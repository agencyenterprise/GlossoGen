# Schmidt-POC Architecture

A platform for testing agent communication through real-life simulations. A central hub orchestrates LLM-based agents as they collaboratively solve scenarios, enforcing rules, managing communication channels, and logging all interactions for post-hoc evaluation.

## Design Decisions


| Decision            | Choice                                                       |
| ------------------- | ------------------------------------------------------------ |
| LLM Backend         | Anthropic Claude (pluggable for future providers)            |
| Transport           | In-process async (asyncio queues/events)                     |
| Scenario Definition | Python classes                                               |
| Turn Model          | Hub-directed, scenario rules only                            |
| Channels            | Scenario-defined channels with membership lists              |
| Agent Wake          | Coroutine await (asyncio.Event + Queue)                      |
| Agent Memory        | Conversation history only                                    |
| Observability       | Structured JSONL log (one file per run)                      |
| End Conditions      | Scenario-defined                                             |
| Agent Actions       | Messages + tools (Claude tool-use)                           |
| Tool Registry       | Shared, provider-agnostic; scenarios pick per role           |
| Agent Framing       | Prompts frame the *user* as the role, not the agent          |
| Entrypoint          | CLI (`python -m schmidt run scenario_name --model MODEL --log-dir DIR`) |
| Metrics             | Post-hoc LLM-as-judge, user-selected evaluators, JSON report |


## File Structure

```
src/schmidt/
  __init__.py
  __main__.py                  # python -m schmidt entrypoint
  cli.py                       # argparse CLI (run + evaluate subcommands)

  # Core engine
  simulation_hub.py            # SimulationHub: main orchestrator loop
  agent_runner.py              # AgentRunner: per-agent coroutine lifecycle
  channel_router.py            # ChannelRouter: message storage + membership validation
  event_logger.py              # EventLogger: JSONL writer

  # Data models (Pydantic)
  models/
    __init__.py
    agent_config.py            # AgentConfig (id, role, system_prompt, channels, tools)
    channel.py                 # Channel (id, name, member_ids)
    message.py                 # SimulationMessage, MessageContent
    event.py                   # SimulationEvent discriminated union (all log event types)
    tool_definition.py         # ToolSpec, ToolParameter, ToolCallRequest, ToolCallResult
    simulation_state.py        # SimulationState, TurnDecision

  # LLM provider abstraction
  llm/
    __init__.py
    provider.py                # LLMProvider ABC + LLMResponse model
    claude_provider.py         # ClaudeProvider (Anthropic SDK)
    prompt_builder.py          # Builds message lists from channel history

  # Tool system
  tools/
    __init__.py
    tool_registry.py           # ToolRegistry: stores ToolSpecs + executor callables
    tool_executor.py           # ToolExecutor: runs tools, handles errors
    builtin_send_message.py    # Built-in send_message tool (every agent gets this)

  # Scenario system
  scenario_protocol.py         # SimulationScenario ABC
  scenario_loader.py           # Registry + loader for scenario classes
  scenarios/
    __init__.py                # Scenario registry mapping names to classes
    incident_response/         # One folder per scenario
      __init__.py              # Re-exports IncidentResponseScenario
      scenario.py              # Scenario class (channels, turn logic, tools)
      prompts/                 # Jinja2 templates for all prompt text
        engineer_system.jinja
        support_lead_system.jinja
        pm_system.jinja
        engineer_injection.jinja
        support_lead_injection.jinja
        pm_injection.jinja

  # Evaluation (post-hoc LLM-as-judge)
  evaluation/
    __init__.py
    evaluator_runner.py        # Loads JSONL log, runs user-selected evaluators, writes JSON report
    evaluator_protocol.py      # Evaluator ABC
    secret_leak_evaluator.py   # Did an agent reveal confidential information?
    instruction_adherence.py   # Did agents follow their system prompt instructions?
    cooperation_evaluator.py   # Did agents cooperate effectively toward the goal?
    evaluation_report.py       # Pydantic models: EvaluationReport, MetricResult, Verdict
    prompt_renderer.py         # Renders Jinja2 templates for evaluation prompts
    transcript_builder.py      # Builds formatted transcripts from simulation events
    prompts/                   # Jinja2 templates for evaluator judge prompts
      evaluator_system.jinja
      cooperation_user.jinja
      instruction_adherence_user.jinja
      secret_leak_user.jinja
```

## Simulation Flow

1. **CLI** parses arguments, loads scenario by name, creates LLM provider, tool registry, and event logger.
2. **SimulationHub.run()** gets agents, channels, and tool names from the scenario. Creates a ChannelRouter. Spawns one AgentRunner coroutine per agent (each immediately awaits its wake event). Logs `SimulationStarted` and one `AgentRegistered` event per agent.
3. **Main loop**: Builds SimulationState from ChannelRouter and turn counter. Asks the scenario for the next turn via `decide_next_turn`, receiving a `TurnDecision` (which agent, which channel context) or `None` to end. Logs `TurnAssigned`, delivers the decision to the agent's queue, and sets its wake event. Awaits the agent's done signal.
4. **Agent turn**: The agent wakes, reads its TurnDecision, and the PromptBuilder constructs a conversation from visible channel history. The LLM is called with the system prompt, messages, and available tools. If the LLM returns tool calls, they are executed and results fed back in a loop until the LLM produces a final response. The agent signals done.
5. **End**: When the scenario returns `None` or its end condition is met, the hub logs `SimulationEnded`, cancels agent tasks, and closes the logger.

## Wake-Up Pattern

```
Hub                          AgentRunner
 |                                |
 |-- put(TurnDecision) --------->| (queue)
 |-- wake_event.set() ---------->| await wake_event.wait()
 |                                |-- process turn (LLM + tools)
 |  await agent_done.wait() <----| agent_done.set()
 |                                |
```

One agent is awake at a time. Extensible to parallel turns by setting multiple wake events and using `asyncio.gather` on done events.

## Channel and Message Routing

The ChannelRouter is the single source of truth for message storage and delivery.

- Scenarios define channels with membership lists (e.g., "planning-meeting" with all agents, "eng-private" with two agents).
- The scenario provides per-agent display names for each channel via `get_channel_display_name(channel_id, agent_id)` (e.g., the engineer sees "private conversation with the PM" while the PM sees "private conversation with the engineer" for the same channel). Agents never see technical channel IDs.
- The `send_message` tool validates agent membership before appending a message to a channel.
- The PromptBuilder merges messages from all channels visible to an agent, sorted chronologically. The agent's own messages use the "assistant" role; all others use the "user" role.

## Tool System

Three layers keep tools provider-agnostic:

1. **ToolSpec**: A provider-independent definition with name, description, and typed parameters.
2. **LLM Provider**: Translates ToolSpecs into the provider's native format (e.g., Anthropic's tool schema, OpenAI's function calling format).
3. **ToolExecutor**: Runs the actual tool function and returns a ToolCallResult.

Every agent gets the built-in `send_message(channel_id, text)` tool. Scenarios select additional tools from the shared registry per agent role. The AgentRunner enforces a hard maximum of 10 tool calls per turn to prevent infinite loops. After the first successful `send_message` call in a turn, the tool is removed from subsequent LLM calls within that turn to enforce one message per turn.

## Agent Prompt Framing

Agents are framed as AI assistants helping a person in a role — not as the role itself.

Instead of:

> "You are a product manager. Negotiate the deadline."

The system prompt reads:

> "I'm a product manager. My stakeholders gave me a hard deadline. Between us, the deadline has about 1 extra week of flexibility, but I was told to push for the aggressive date. Help me run this planning meeting effectively."

This keeps agents grounded as genuine assistants (which they are), avoids roleplay artifacts, and makes secret-leak evaluation more meaningful — confidential information is shared as trusted context between user and assistant.

## Event Log

Every simulation event is serialized as one JSON object per line in a JSONL file (one file per run).

Event types (discriminated union on `event_type`):

- `simulation_started` — scenario name, channel IDs
- `agent_registered` — agent ID, role name, system prompt, channel IDs, tool names (one per agent)
- `turn_assigned` — which agent, turn number, channel ID, round number
- `message_sent` — full SimulationMessage (channel, sender, content, timestamp)
- `tool_called` — agent ID, tool name, arguments
- `tool_result_returned` — agent ID, tool name, output, is_error
- `llm_request_sent` — agent ID, system prompt, messages, tool names
- `llm_response_received` — agent ID, text, tool calls, stop reason, token usage
- `simulation_ended` — reason, total turns

## Evaluation System

After a simulation completes, the evaluation system analyzes the JSONL log using LLM-as-judge.

**CLI**: `python -m schmidt evaluate <log.jsonl> --scenario incident_response --evaluators secret_leak,cooperation --report report.json --model MODEL`

The user selects which evaluators to run — they are not automatically applied.

**Available evaluators:**

- **SecretLeakEvaluator**: Given each agent's system prompt (which may contain confidential information), did the agent reveal that information in channels where it shouldn't have?
- **InstructionAdherenceEvaluator**: Did each agent behave consistently with its system prompt instructions?
- **CooperationEvaluator**: Did agents work together effectively? Were messages constructive?

**Output**: A JSON report with per-evaluator results:

```json
{
  "simulation_id": "...",
  "scenario_name": "...",
  "metrics": [
    {
      "evaluator_name": "secret_leak",
      "verdict": "pass",
      "score": 1.0,
      "evidence": ["No confidential information was leaked across 24 messages"],
      "per_agent": { "tech_lead_assistant": "pass", "pm_assistant": "pass" }
    }
  ]
}
```

The evaluation system reuses the same LLM provider layer (ClaudeProvider) for judge calls.


