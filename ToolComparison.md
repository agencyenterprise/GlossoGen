# Tool Comparison

A competitive landscape analysis of multi-agent simulation and orchestration frameworks, compared against schmidt-poc.

## Summary Table


| Framework             | Focus                                     | Agents                        | Communication                                 | Coordination                                                                         | Eval                       |
| --------------------- | ----------------------------------------- | ----------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------- |
| **schmidt-poc**       | Realistic workplace sims with hidden info | 3-5                           | MCP tools (async, channel-based)              | Autonomous + game clock rounds                                                       | LLM-as-judge post-hoc      |
| **CAMEL**             | Role-playing research                     | 2 (core) / N (Workforce, OWL) | Direct alternating turns                      | Strict ping-pong                                                                     | Human + GPT-4 as judge     |
| **AgentVerse**        | Configurable multi-agent tasks            | N                             | Environment-mediated                          | 4-stage loop (recruit/decide/execute/evaluate)                                       | In-loop LLM evaluator      |
| **OASIS**             | Social media simulation                   | Up to 1M                      | Indirect (posts/feeds)                        | Async probabilistic activation                                                       | Scenario-specific post-hoc |
| **HiddenBench**       | Hidden-profile group decisions            | 3-7                           | Synchronous rounds                            | Fixed turn-taking (5-20 rounds, optimal at 15)                                       | Pre/post accuracy          |
| **AutoGen / AG2**     | Flexible agent infrastructure             | N                             | Pub/sub + RPC; manager-controlled group chats | 5 speaker-selection strategies; distributed mode changes transport, not coordination | None built-in              |
| **CrewAI**            | Role-based task crews                     | N                             | Task output chaining                          | Sequential or hierarchical with manager                                              | Task completion metrics    |
| **MetaGPT**           | SOP-driven workflows                      | N                             | Shared message pool (pub/sub)                 | Artifact dependency graph                                                            | None built-in              |
| **Generative Agents** | Believable social behavior                | 25                            | Proximity-triggered dialogue                  | Global game clock                                                                    | Human TrueSkill ratings    |
| **AgentTorch**        | Population-scale modeling                 | Millions                      | Rule-based interactions                       | Tensor-parallel substeps                                                             | Gradient-based calibration |
| **ChatArena**         | Language games (deprecated)               | N                             | Per-player observations                       | MDP-style env                                                                        | Reward function            |
| **LangGraph**         | Stateful agent orchestration              | N                             | Shared graph state (key-value channels)       | Build-time graph topology + conditional edges                                        | None built-in (LangSmith)  |
| **OpenAI Agents SDK** | Production agent pipelines                | N                             | Handoffs + agents-as-tools                    | Sequential Runner loop; LLM decides handoffs                                         | None built-in (tracing)    |
| **Letta**             | Stateful long-running agents              | N                             | Point-to-point async/sync + shared memory blocks | Reactive (message-triggered); developer-defined patterns                          | None built-in              |
| **Haystack**          | RAG, search, agentic apps                 | N                             | Coordinator calls subagents as tools          | Hierarchical coordinator LLM                                                         | RAG metrics + LLM-as-judge |


## Detailed Findings

### CAMEL

**Repo**: [camel-ai/camel](https://github.com/camel-ai/camel) | **Paper**: NeurIPS 2023 (arXiv:2303.17760)

Two LLM agents are assigned complementary roles (AI User and AI Assistant) and converse autonomously to complete a task. The key contribution is **inception prompting** — a prompt engineering technique that keeps agents on-task and in-role without human supervision. System prompts embed explicit anti-patterns ("never flip roles", "never repeat instructions") and structured response formats.

- **Coordination**: Strict turn-taking between two agents. Each `step()` call produces one full exchange cycle (assistant response + user's next instruction).
- **Termination**: Token-based (`<CAMEL_TASK_DONE>`) or max iteration count.
- **Evaluation**: Human raters + GPT-4 as judge across 25K conversations. Optional critic-in-the-loop as a third agent.
- **Scale**: Dyadic by default. A newer Workforce module supports N agents with task routing, but lacks channel-based communication. The OWL sub-project (Optimized Workforce Learning) ranked #1 on the GAIA benchmark for open-source multi-agent frameworks (58.18 at launch in March 2025, updated to 69.09 in April 2025).

**vs schmidt-poc**: CAMEL is dyadic with strict turn-taking; we support N agents communicating through shared channels with no central turn controller. Their inception prompting technique (explicit behavioral constraints in system prompts) is a useful pattern for preventing agent failure modes like role-flipping or narration.

---

### AgentVerse

**Repo**: [OpenBMB/AgentVerse](https://github.com/OpenBMB/AgentVerse) | **Paper**: ICLR 2024

Two frameworks in one codebase: a task-solving framework (dynamic agent teams) and a simulation framework (emergent behavior observation). The task-solving side uses a 4-stage pipeline (Expert Recruitment → Collaborative Decision-Making → Action Execution → Evaluation) with in-loop LLM evaluation that feeds back into team composition.

- **Agents are not autonomous**: A centralized environment loop orchestrates everything. Agents never decide on their own to speak — the environment invokes them. Closer to a turn-based game engine than an event-driven system.
- **Dynamic recruitment**: The task-solving environment adjusts team composition between iterations based on evaluator feedback — an interesting pattern our fixed-role scenarios don't support.
- **Pluggable rule components**: The simulation environment decomposes coordination into Order (turn selection), Visibility (who sees whom), Selector (message filtering), Updater (message routing), and Describer (per-agent context generation).
- **No channel/room abstraction**: All agents share a single conversation. Messages have a receiver set (defaults to broadcast) for targeted routing, but there are no concurrent conversation spaces or topic isolation.
- **Key result**: Multi-agent groups outperform single agents on HumanEval (+5.5%), tool utilization (3/10 → 9/10), and constrained text generation.

**vs schmidt-poc**: AgentVerse agents are passive responders invoked by a central loop; ours are autonomous processes that decide when to speak. Their agents cannot initiate communication or operate concurrently on different topics, making it unsuitable for realistic workplace simulations where timing and initiative matter. Their lack of channels means information asymmetry must be achieved through per-message receiver sets rather than structural isolation — fragile compared to our channel membership model.

---

### OASIS

**Repo**: [camel-ai/oasis](https://github.com/camel-ai/oasis) | **Paper**: arXiv 2411.11581

Social media simulation platform where LLM agents interact on replicas of Twitter/X and Reddit. Studies emergent social phenomena (information spread, polarization, herd behavior) at scale.

- **Architecture**: Environment server (SQLite), recommendation system (TwHIN-BERT for Twitter, hot-score for Reddit), agent module (extends CAMEL's ChatAgent), time engine, scalable inferencer (vLLM + GPU manager).
- **Scale**: Up to 1M agents on 27 A100 GPUs (~~18h per timestep). 100K agents on 5 A100s (~~3h per timestep).
- **No direct agent-to-agent communication**. All interaction is mediated through the platform (posts, comments, likes, follows). The recommendation system is load-bearing for emergent behavior — removing it causes information propagation to stall.
- **Temporal activation**: Each agent has a 24-dimensional hourly activity probability vector (from real user data). Agents activate probabilistically, not via turn-taking.
- **Key finding**: LLM agents exhibit stronger herd behavior than real humans, specifically **negative herding** — agents pile onto downvotes and criticism more than real humans do. This effect intensifies with scale, which is directly relevant to pressure-driven simulations where agents may exhibit unrealistic conformity.

**vs schmidt-poc**: Fundamentally different communication model (platform-mediated vs channel-based). Their probabilistic temporal activation is more realistic than our uniform random reaction delays — scenarios could define per-agent, per-round activity profiles. Their recommendation/filtering layer is relevant if scenarios grow beyond 3-5 agents: agents see summaries of low-priority channels but full messages from high-priority ones.

---

### HiddenBench

**Paper**: arXiv 2505.11556 | **Dataset**: [HuggingFace - YuxuanLi1225/HiddenBench](https://huggingface.co/datasets/YuxuanLi1225/HiddenBench)

A 65-task benchmark grounded in the **Hidden Profile paradigm** from social psychology. Agents hold asymmetric information; shared information deliberately contains misleading cues favoring the wrong answer. The correct answer requires integrating private (unshared) information across agents. Agents are not told their information differs. Tested across 15 frontier LLMs (GPT, Gemini, Qwen, Llama families).

- **Setup**: N∈{3,4,5,6,7} agents, T∈{5,10,15,20} discussion rounds (performance peaks at T=15, degrades at T=20 as extended discussion reinforces incorrect consensus). Pre-discussion and post-discussion decisions. Agents make individual choices.
- **Metrics**:
  - **Information Integration Gain**: post-discussion accuracy minus pre-discussion baseline
  - **Collective Reasoning Gap**: full-info single-agent accuracy minus post-discussion group accuracy
- **Key findings**:
  - Multi-agent LLMs achieve **30.1% accuracy** under distributed information vs **80.7%** for a single agent with complete information
  - **Reveal-All intervention** (force agents to disclose all facts immediately) raises accuracy to **96.7%** — proving the bottleneck is recognition of information asymmetry, not reasoning ability
  - Performance **degrades as group size increases**: +34.8% improvement at N=3 drops to +0.6% at N=7
  - Prompting strategies (CoT, cooperation framing) yield almost no improvement
  - Core failure: agents cannot recognize **latent information asymmetry** — they don't reason about what others might know but haven't expressed
  - Model scale and reasoning capabilities do not consistently predict collective reasoning ability
  - Best model: Gemini-2.5-Pro (post-discussion accuracy 0.671, smallest gap to full-info at -0.310)

**vs schmidt-poc**: The most conceptually aligned framework. Tests the same cognitive challenge as car_recall: private facts must be pooled for a correct group decision. Their structural design (shared info points to the wrong answer) is more rigorous than ours. Their metrics (Information Integration Gain, Collective Reasoning Gap) are directly applicable to our fact_surfacing evaluator. Their 30.1% finding is a published baseline we can compare against. The Reveal-All finding (96.7% when forced to disclose) confirms the bottleneck is information surfacing behavior, not reasoning — validating our focus on fact_surfacing evaluation. The group-size degradation finding (N=3 best, N=7 worst) should inform our scenario agent counts.

---

### AutoGen / AG2 (Microsoft Agent Framework)

**Repo**: [microsoft/autogen](https://github.com/microsoft/autogen) | In late 2024, the original creators departed Microsoft and established **AG2** as a community-driven fork. The Microsoft side rebranded as the "Microsoft Agent Framework" (public preview, GA targeted Q1 2026).

SDK and runtime for multi-agent applications. Two layers: a **Core runtime** (message routing via RPC and pub/sub) and an **AgentChat layer** (high-level group conversations).

- **Group chats function like moderated meetings, not Slack channels.** A central manager controls who speaks. Non-selected agents passively buffer messages. Agents **cannot choose to stay silent** (no response = RuntimeError).
- **Five group chat strategies**: round-robin, LLM-based speaker selection, swarm handoff, MagenticOne orchestrator, and graph flow. `select_speaker()` can return multiple names for parallel execution.
- **Agents are not autonomous**: The framework runs the tool-use loop — it gathers tool schemas, calls the LLM, parses function calls, executes tools, and feeds results back. Optional reflection step after tool execution.
- **Distributed mode** (gRPC): Agents can run on separate processes connected via a central host, but **distribution does not change the coordination model**. The same central manager sends `RequestToSpeak` to one agent at a time. The core runtime's pub/sub primitives *could* support autonomous agents, but none of the built-in patterns use them that way.
- **Nested teams**: A `Team` can be a participant in another team's group chat, enabling hierarchical topologies.

**vs schmidt-poc**: AutoGen agents are passive responders managed by a central loop, even in distributed mode; ours are autonomous processes that decide when to speak. Their "group chat" is a moderated meeting where a manager calls on agents; our channel-based system allows concurrent, unsolicited communication. Their agents cannot initiate conversation, remain silent, or observe a channel and decide to chime in. Their gRPC distributed runtime provides cross-process hosting but not autonomy — a central manager still decides who speaks. Our MCP-over-HTTP design provides both distribution and autonomy in one design.

---

### CrewAI

**Repo**: [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | **Docs**: [docs.crewai.com](https://docs.crewai.com)

Framework for orchestrating role-playing AI agents in teams called "Crews." Agents are defined by role, goal, and backstory. Two layers: Crews (autonomous teams) and Flows (event-driven workflow orchestration).

- **Coordination**: Sequential (task outputs chain forward) or hierarchical (a manager LLM delegates tasks and validates outcomes).
- **All communication is point-to-point, no broadcast.** Two delegation tools (`DelegateWorkTool`, `AskQuestionTool`) allow an agent to hand work or ask a question to exactly one coworker by role name. No "send to all" or channel mechanism.
- **Remote delegation via A2A protocol**: Agents can delegate to external services (another CrewAI crew or any A2A-compatible endpoint) via Google's Agent-to-Agent protocol. The remote side is fully opaque — it runs its own LLM loop independently. Still strictly 1-to-1.
- **Context passing**: In sequential mode, task N's output is passed as context to task N+1. Pipeline chaining, not interactive communication.
- **Memory system**: Short-term (context window), long-term (persistent embedder), entity (tracks people/concepts), and unified shared store. All pull-based — agents query on their turn, no push notifications.
- **Tools**: 30+ built-in tools. Native MCP support.

**vs schmidt-poc**: CrewAI's communication model is the inverse of ours. We provide shared channels where multiple agents observe and react in real time; CrewAI provides point-to-point delegation to exactly one agent. Only one agent is active at a time — no concurrent communication, no unsolicited messages, no information asymmetry through structure. Group dynamics (consensus building, information pooling, side conversations) are structurally impossible. Their A2A protocol support is the closest thing to external-process agents among the frameworks listed, but it's for cross-service delegation, not for running a group of autonomous agents.

---

### MetaGPT

**Repo**: [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | **Paper**: ICLR 2024 (arXiv:2308.00352) | **AFlow**: ICLR 2025 Oral (213 orals / 11,672 submissions = 1.82%)

Multi-agent framework modeled on a software company. Core philosophy: "Code = SOP(Team)." Encodes Standard Operating Procedures into agent behavior — agents follow structured professional workflows rather than free-form conversation. Launched **MGX** (MetaGPT X) in February 2025 as a commercial product.

- **Roles**: Product Manager, Architect, Project Manager, Engineer, QA Engineer. Each has required output schemas and trigger conditions.
- **Coordination**: Shared message pool (publish-subscribe). Agents publish structured outputs; other agents subscribe based on role-specific interests. Assembly-line workflow (PM → Architect → PM → Engineer → QA).
- **Structured output as coordination**: Agents produce mandatory documents (PRDs, system designs, API specs) — not free text. This forces precision at each handoff and eliminates ambiguity.
- **Executable feedback**: The Engineer runs generated code against unit tests, receives concrete errors, and iterates (up to 3 retries) using memory of requirements and prior code.

**vs schmidt-poc**: MetaGPT's structured-output-as-coordination is the most transferable idea. Our agents communicate in free text, which makes evaluation harder. For specific scenarios, requiring agents to produce typed artifacts (e.g., a `submit_report` tool with structured fields for the car_recall PR agent) gives evaluators cleaner signal than parsing free-text messages.

---

### Generative Agents (Stanford)

**Repo**: [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents) | **Paper**: UIST 2023 (arXiv:2304.03442)

25 LLM agents autonomously live daily lives in a sandbox world called Smallville. The goal is believable human behavior simulation, not task completion.

- **Memory system** (three components stored in a unified memory stream):
  - **Observation**: Append-only log of perceived events, each with an importance score (1-10, LLM-assigned)
  - **Reflection**: Triggered when cumulative importance exceeds 150. LLM generates high-level insights from recent memories, stored back in the stream as tree nodes citing source observations
  - **Planning**: Top-down recursive decomposition (day → hours → 5-15 min blocks). Plans are reactive — re-planned when new observations trigger reactions
- **Retrieval**: `score = α_recency × recency + α_importance × importance + α_relevance × relevance` (all α=1). Recency uses exponential decay (factor 0.995 per simulated hour). Importance is LLM-assigned (1-10). Relevance is cosine similarity of embeddings. All normalized to [0,1].
- **Reflection tree structure**: Reflections form trees where leaf nodes are base observations and non-leaf nodes are increasingly abstract insights. This compounding structure means reflections build on other reflections, producing multi-level abstraction (~2-3 reflections per simulated day).
- **Interaction**: Proximity-based. When agents perceive each other, retrieved memories about that person inform the decision to engage. Turn-by-turn dialogue with full conversation stored in both agents' memory streams.
- **Evaluation**: 100 human evaluators ranked 5 conditions via TrueSkill. Full architecture (mu=29.89) beat human crowdworkers (mu=22.95). Hallucination rate: 1.3%. Ablation studies showed each component (observation, reflection, planning) contributes independently to believability.
- **Follow-up**: Scaled to 1,052 agents initialized from real interview data. LLM agents replicated source individuals' survey responses at 85% accuracy, validating the architecture for realistic behavioral modeling.

**vs schmidt-poc**: Shares our game-clock-driven round progression and autonomous agent communication. Their memory stream with importance scoring and periodic reflection is the most relevant technique for longer simulations. Our agents rely on the LLM context window — for scenarios beyond a few rounds, a memory layer that filters what agents "remember" between rounds would produce more realistic behavior.

---

### AgentTorch (MIT)

**Repo**: [AgentTorch/AgentTorch](https://github.com/AgentTorch/AgentTorch) | **Paper**: AAMAS 2025 Oral — "On the Limits of Agency in Agent-based Models" (arXiv:2409.10568)

Framework for Large Population Models — agent-based simulations of millions of interacting agents, built on PyTorch. The entire simulation is a differentiable computation graph.

- **Architecture**: YAML config declares agent types (with tensor shapes and `learnable: true/false` flags), substep sequences (Observation → Action/Policy → Transition), and network topology.
- **LLM integration via archetypes**: Groups agents into N behavioral archetypes (e.g., 7). One LLM call per archetype, then behavior is sampled across the full population via tensor operations. 7 LLM calls serve millions of agents.
- **Differentiability**: Agent properties can be PyTorch parameters with gradients. The full simulation loop is differentiable via autograd, enabling gradient-based calibration against real-world data.
- **Scale**: Millions of agents on commodity GPUs. All agent states are tensors; updates are vectorized batch operations.
- **Applications**: COVID-19 epidemiology (8.4M agents modeling NYC employment behavior), vaccine distribution, predator-prey dynamics, urban mobility, supply chains.

**vs schmidt-poc**: Fundamentally different design point — AgentTorch optimizes for scale (millions of simple agents) via GPU parallelism; we optimize for depth (fewer agents with rich multi-turn reasoning and tool use). Their archetype pattern (few LLM calls mapped to many agents) is potentially useful if we ever need crowd simulations with background agents that don't need full autonomy.

---

### ChatArena (Deprecated)

**Repo**: [Farama-Foundation/chatarena](https://github.com/Farama-Foundation/chatarena) | Deprecated August 2025 due to lack of widespread community adoption.

Multi-agent language game environment. Interactions modeled as an MDP with four abstractions: Arena, Environment, Player, Language Backend.

- **MessagePool as state**: All messages go through a shared pool. `get_observation(player_name)` returns only messages visible to that player at the current turn. Per-player, per-turn visibility filtering enables information asymmetry.
- **Turn modes**: Sequential (round-robin) or parallel (simultaneous secret actions, visibility filtered within the same turn).
- **Moderator role**: An LLM-powered agent with full visibility that injects messages, enforces rules, and determines termination.
- **Built-in games**: Chameleon (social deduction), Rock-Paper-Scissors, Tic-Tac-Toe, NLP Classroom, PettingZoo integrations.
- **Limitations**: No persistent memory, no training loop, no structured output parsing, deprecated with no successor.

**vs schmidt-poc**: Had the closest architectural shape — MDP-style environments with per-player observation rendering. Our channel membership + per-agent display names achieve the same information asymmetry. Their per-turn visibility changes (not just per-channel) could enable scenarios where information access changes dynamically mid-simulation.

---

### LangGraph

**Repo**: [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)

Low-level orchestration framework for building stateful, long-running agents. Execution model derived from Google's Pregel paper on distributed graph processing. Operates independently of the LangChain library.

- **Communication via shared graph state**: All agents read from and write to a typed key-value store (TypedDict/Pydantic). No direct peer-to-peer messaging. Updates merge via reducer functions (e.g., `add_messages` appends to a shared list). Private state channels can restrict keys to specific nodes.
- **Coordination is graph-topology-defined**: Fixed edges, conditional edges (routing functions that read state), or `Command` objects (node returns both a state update and a routing decision atomically). Execution proceeds in Pregel-style "super-steps" — all active nodes execute in parallel, then outputs propagate. No emergent coordination.
- **Agents are passive at the graph level**: Within a node, an agent can run an autonomous tool-calling loop. But nodes only execute when the runtime delivers a message via an edge. Agents cannot spontaneously initiate a turn, interrupt another agent, or choose to stay silent.
- **Multi-agent patterns**: Supervisor (subagents exposed as tools to a coordinator), peer network (agents connected by conditional edges), subgraphs (modular state isolation), map-reduce (fan-out via `Send` primitive). All patterns are developer-defined topology, not emergent.
- **Information asymmetry**: Limited — per-node input schemas can restrict which state keys a node sees, and subgraphs maintain separate schemas. But asymmetry is structural (defined at build time), not dynamic (runtime-determined per-agent channel membership).

**vs schmidt-poc**: LangGraph agents are graph nodes activated by the runtime; ours are persistent processes that decide when to act. Their state-based communication (all agents mutate a shared snapshot) is fundamentally different from our channel-based model (agents subscribe to specific channels and observe message streams). Information asymmetry requires explicit schema engineering at build time rather than runtime channel membership. No round structure, no injection mechanism, no evaluation. Their first-class **checkpointing** (full state snapshot per super-step, resumable from any checkpoint) is directly relevant — a checkpoint-per-round model would let crashed simulations resume rather than restart from scratch. Their **`interrupt()` / resume** mechanism could inspire a pause/resume capability for scenario designers to inspect state and inject custom messages mid-simulation.

---

### OpenAI Agents SDK

**Repo**: [openai/openai-agents-python](https://github.com/openai/openai-agents-python)

Lightweight framework (formerly Swarm) for building production multi-agent workflows. Three core primitives: Agents (LLM + instructions + tools), Handoffs (transfer of control), and Guardrails (input/output validation). Targets OpenAI models natively; 100+ LLMs via LiteLLM in beta.

- **Communication via handoffs only**: The active agent calls a handoff tool to transfer control to another agent. The new agent receives the full conversation history (optionally filtered). No two agents ever run concurrently. No message bus, no shared channels, no peer-to-peer communication.
- **Agents-as-tools**: A manager agent can invoke a sub-agent as a tool call. The sub-agent runs to completion and returns its result. The manager remains in control throughout.
- **Coordination by Runner loop**: A sequential `Runner` loop calls the current agent's LLM, executes tool calls, processes handoffs, and repeats. The LLM drives within-turn decisions; the Runner controls scheduling. `max_turns` is the only governance knob.
- **Agents are passive**: They execute only when the Runner invokes them. Cannot spontaneously start a turn, send unprompted messages, or run in parallel with other agents.
- **No information asymmetry**: A single shared `RunContextWrapper.context` object is available to all agents in a run. Conversation history flows fully to receiving agents by default. `handoff_input_filter` can trim history, but there is no structural mechanism for different world views.
- **Built-in tracing**: Automatic span-based tracing for runs, LLM calls, tool calls, handoffs. Exports to 21+ observability platforms. No built-in evaluation.

**vs schmidt-poc**: The OpenAI Agents SDK is a sequential pipeline where one agent is active at a time; we run all agents concurrently as independent processes. Their handoff model is strictly hierarchical (triage → specialist or manager → worker); our channel model supports peer-to-peer group discussion. No information asymmetry, no round structure, no simulation framing. Their **guardrails** (async validation that can block agent output before it's delivered) could be applied to `send_message` for preventive leak detection rather than just post-hoc evaluation. Their **span-tree tracing** (parent-child relationships between events, not just flat logs) would make the frontend timeline richer — linking which `send_message` calls were caused by which reasoning block or round injection.

---

### Letta

**Repo**: [letta-ai/letta](https://github.com/letta-ai/letta) | **Paper**: "MemGPT: Towards LLMs as Operating Systems" (arXiv:2310.08560)

Stateful agent platform (originally MemGPT) focused on persistent memory across long-running conversations. Treats the context window as a CPU cache — an OS-inspired virtual context management system moves information between memory tiers.

- **Three-tier memory architecture**: (1) **Core memory** — structured blocks prepended to the system prompt, always visible, agents read/write via tools. (2) **Archival storage** — semantically searchable, append-only long-term database. (3) **Recall storage** — all past messages persisted; older messages evicted from context and compressed into summaries.
- **Multi-agent communication**: Three built-in tools — `send_message_to_agent_async` (fire-and-forget), `send_message_to_agent_and_wait_for_reply` (synchronous), `send_message_to_agents_matching_all_tags` (broadcast to tagged group). **Shared memory blocks** can be attached to multiple agents for real-time shared state.
- **Agents are reactive, not autonomous**: The agent loop activates when a message arrives. One agent can trigger another via messaging tools, creating activation chains, but the chain always starts from an external message. Agents do not poll or self-initiate.
- **No information asymmetry by design**: No channel membership, no per-agent visibility rules. Each agent's private memory provides incidental isolation, but there is no structural mechanism for controlled information withholding.
- **No round structure or evaluation**: No game clock, no injection mechanism, no built-in evaluators.

**vs schmidt-poc**: Letta and schmidt-poc address different problems — Letta is a production agent infrastructure for persistent memory; we are a simulation platform for group dynamics under information asymmetry. Their tiered memory architecture is the most relevant technique for extending our simulations beyond a few rounds, where agents risk losing earlier facts from the context window. Their shared memory blocks are the closest analog to a shared channel, but blocks are freeform key-value stores with no message ordering or change notifications — agents must explicitly query rather than observe passively. Two high-value, low-effort ideas: (1) a **per-agent notes block** — a bounded string in the system prompt that the agent rewrites each round via an MCP tool, surviving context window overflow; (2) a **shared bulletin board** — a bounded, always-visible state document (distinct from channels, which are append-only history) that any agent can update, giving all participants shared situational awareness without re-reading full channel history.

---

### Haystack

**Repo**: [deepset-ai/haystack](https://github.com/deepset-ai/haystack)

Open-source framework for building production RAG, semantic search, and agentic applications. Vendor-agnostic across LLM providers. Primary focus is retrieval-augmented pipelines rather than multi-agent simulation.

- **Agent model**: A loop-based `Agent` component that calls an LLM, executes tools, and iterates until an exit condition fires (plain text response or specific tool call). Configurable `max_agent_steps` and optional human-in-the-loop confirmation gates.
- **Multi-agent via coordinator pattern**: A specialist `Agent` is wrapped in a `ComponentTool` and exposed as a callable tool to a coordinator `Agent`. The coordinator invokes subagents within its reasoning loop. No peer-to-peer communication — only the coordinator sees subagent results (final answer only, not reasoning trace).
- **Agents are passive**: They run only when called by the coordinator or by pipeline input. No background execution, no event listeners, no scheduling.
- **No information asymmetry**: No mechanism to scope visibility per agent. Every agent sees exactly what is passed to it via tool inputs.
- **Evaluation**: Built-in evaluators for RAG quality (exact match, MRR, MAP, recall, faithfulness, context relevance). LLM-as-judge support. But evaluation targets pipeline outputs, not agent behavior or multi-agent coordination.
- **Tools**: Python functions via `@tool` decorator, components wrapped as `ComponentTool`, MCP servers via `Toolset`.

**vs schmidt-poc**: Haystack is a RAG/search application framework, not a simulation platform. Multi-agent support is strictly hierarchical (coordinator calls subagents as tools). No concurrent agent execution, no peer-to-peer communication, no information asymmetry, no round structure. Their RAG evaluation primitives (faithfulness, context relevance) operate on a different dimension than our behavioral evaluators (secret_leak, cooperation, fact_surfacing). Their **statement decomposition** pattern (break output into atomic claims, score each independently, average) could make evaluators like `cooperation` or `instruction_adherence` more granular — decomposing agent behavior into individual observable claims before scoring. Their **`EvaluationRunResult.comparative_detailed_report()`** (side-by-side metric diffs across runs) is a useful pattern for iterating on scenario design and comparing models.

---

## What Schmidt-POC Does That Nobody Else Does


| Capability                                             | Details                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MCP-based agent isolation with true autonomy**       | Agents are real Claude Code processes connected via Streamable HTTP. No other framework does this — most use direct API calls in a Python loop. Even AutoGen's gRPC distributed runtime, which runs agents on separate processes, still uses centralized turn control (`RequestToSpeak`). Our agents independently call `check_messages` and `send_message`, combining distribution with autonomy in one design. |
| **"Agents don't know it's a simulation" framing**      | The `comms` MCP server disguised as a messaging system is unique. Other frameworks either tell agents they're in a game or don't address the framing.                                                                                                                                                                                                                                                            |
| **Round injections with parameterized pressure knobs** | Scenario-driven event injection mid-simulation with configurable pressure dials (time pressure, goal pressure, regulator pressure via knobs JSON files). Most frameworks use static initial prompts.                                                                                                                                                                                                             |
| **Per-agent channel display names**                    | The same channel renders differently to each agent (e.g., "private conversation with the PM" vs "private conversation with the engineer"). Not found elsewhere.                                                                                                                                                                                                                                                  |
| **Domain-specific post-hoc evaluation suite**          | Evaluators like secret_leak, fact_surfacing, report_divergence, and decision_correctness are more targeted than anything in the landscape.                                                                                                                                                                                                                                                                       |


## What's Closest to Us

**HiddenBench** is the most conceptually aligned. It tests the same cognitive challenge as car_recall: agents hold private facts that must be pooled for a correct group decision. Their headline finding — 30.1% multi-agent accuracy vs 80.7% single-agent-with-full-info — validates that this problem space matters. Agents fail to surface and reason about what others might know. Their metrics (Information Integration Gain, Collective Reasoning Gap) are directly applicable to our fact_surfacing evaluator.

**ChatArena** (now deprecated) had the closest architectural shape — MDP-style environments with per-player observation rendering for information asymmetry. Our channel membership + per-agent display names achieve the same goal.

**Generative Agents** (Stanford) shares our game-clock-driven round progression and autonomous agent model.

## Actionable Learnings

### 1. From HiddenBench — Adopt their evaluation metrics

Their "Information Integration Gain" (post-discussion accuracy minus pre-discussion baseline) and "Collective Reasoning Gap" (full-info single-agent accuracy minus post-discussion group accuracy) are rigorous, well-defined metrics. Add a pre-simulation baseline step: give one agent ALL facts and measure if it reaches the correct decision alone, then compare against the multi-agent outcome. This makes fact_surfacing and decision_correctness results much more interpretable.

### 2. From HiddenBench — Use their 30.1% finding as a benchmark

Running car_recall with their hidden-profile framing (shared info pointing to the wrong answer) lets us directly compare results and validate or challenge their findings with our more realistic autonomous setup vs their rigid turn-taking.

### 3. From Generative Agents — Memory stream with importance scoring

Their memory architecture (append-only log + retrieval scored by `α_recency × recency + α_importance × importance + α_relevance × relevance`, all α=1, recency decay factor 0.995/hr, importance LLM-assigned 1-10, relevance via cosine similarity, all normalized [0,1] + periodic reflection triggered at cumulative importance threshold of 150) is relevant for extending scenarios beyond a few rounds. A memory layer that filters what agents "remember" between rounds could produce more realistic behavior in longer simulations. Reflections form tree structures where insights compound — this means agents develop increasingly abstract understanding over time rather than just accumulating raw observations.

### 4. From MetaGPT — Typed artifacts instead of free-text messages

Certain channels or tools could produce typed outputs (e.g., a `submit_report` tool with structured fields for the car_recall PR agent's report to the regulator), giving evaluators cleaner signal than parsing free-text messages.

### 5. From OASIS — Non-uniform temporal activation

Their per-agent hourly activity probability vectors produce more realistic timing than our uniform random reaction delays. Scenarios could define per-agent, per-round activity profiles (e.g., the engineer is more active in early rounds, the PM ramps up in later rounds).

### 6. From OASIS — Notification priority/filtering layer

In longer simulations with many channels, agents could see summaries of low-priority channels but full messages from high-priority ones. Not needed at current scale (3-5 agents), but relevant if scenarios grow.

### 7. From CAMEL — Explicit anti-pattern constraints in prompts

Adding "never do X" constraints to agent system prompts based on observed failure modes (breaking character, narrating instead of acting, attempting nonexistent tools). Their inception prompting technique is a systematic approach to preventing common agent misbehaviors.

### 8. From AutoGen — Agents cannot stay silent, and that's a problem

AutoGen's group chat enforces that every selected agent **must** produce a response (no response = RuntimeError). This design reveals a real limitation: agents cannot express "I have nothing useful to add." In realistic workplace simulations, the ability to stay silent or defer is important — not every participant speaks in every meeting round. Our autonomous model naturally handles this (agents only speak when they call `send_message`), which is a meaningful advantage for realistic behavior.

### 9. From AutoGen — Reflection step after tool use

AutoGen's `AssistantAgent` supports an optional reflection step: after executing tools, the LLM is called again to summarize or review tool results before producing the final response. This is relevant for scenarios where agents use tools (e.g., scenario-specific MCP tools) — a reflection pass lets the agent reason about tool output before composing its message to the group, producing more coherent communication.

### 10. From AutoGen — Distribution without autonomy is insufficient

AutoGen's gRPC distributed runtime proves that running agents on separate processes/machines does not inherently produce autonomous behavior. Their distributed group chat sample runs a manager, writer, and editor on three processes connected via gRPC, but the coordination is identical to single-process: a central manager sends `RequestToSpeak` to one agent at a time, non-selected agents passively buffer messages, and no agent can initiate communication. The core runtime's pub/sub primitives (`publish_message`) *could* support autonomous agents, but none of the built-in patterns use them that way. This validates our architectural choice: our MCP-over-HTTP design provides both distribution (agents are separate Claude Code processes) and autonomy (agents independently decide when to call `check_messages` and `send_message`) as a single integrated capability, rather than treating them as orthogonal concerns that can be combined later.

### 11. From LangGraph — Checkpoint-per-round for crash recovery

LangGraph snapshots full graph state at every super-step, enabling resume from any checkpoint. A checkpoint-per-round model for schmidt-poc would serialize `ChannelRouter` state and `AgentSession` counters after each round advancement. Long multi-round simulations are expensive to restart from scratch — checkpointing lets a crashed simulation resume from the last completed round.

### 12. From LangGraph — Pause/resume for scenario designer control

LangGraph's `interrupt()` mechanism pauses execution and surfaces state for human inspection before resuming. A similar capability — an `asyncio.Event` that the game clock awaits before advancing rounds, controllable via REST endpoints — would let scenario designers pause a live simulation, inspect channel state, and optionally inject custom messages before continuing.

### 13. From OpenAI Agents SDK — Preventive guardrails on send_message

Their guardrails (async validation that can block agent output) applied to our `send_message` MCP tool would enable preventive leak detection — catching information leaks before they reach the channel, not just scoring them post-hoc. A guardrail could run an LLM judge on outgoing messages against the agent's confidentiality constraints and block or flag violations in real time.

### 14. From OpenAI Agents SDK — Span-tree tracing for richer event logs

Their tracing system captures parent-child relationships between events (which tool call was caused by which LLM generation). Our flat JSONL event log makes it hard to answer "what triggered this message?" A span-tree structure would let the frontend render causal chains: round injection → agent notification → reasoning → tool call → channel write.

### 15. From Letta — Per-agent notes block for cross-round memory

A bounded string in the agent's system prompt that the agent rewrites each round via an MCP tool (`update_notes`). Solves the core problem of context window overflow in long simulations — agents can distill key facts into persistent notes that survive round boundaries. Low implementation cost: a string field on `AgentSession`, rendered into the Jinja2 prompt template.

### 16. From Letta — Shared bulletin board distinct from channels

A bounded, always-visible state document that any agent can update — distinct from channels (which are append-only message history). Useful for shared situational awareness: "current consensus", "open questions", "decisions made". Agents see the current state without re-reading hundreds of messages. Implementation: a string in `SimulationRuntime`, an MCP tool `update_bulletin`, and a `{{ bulletin_board }}` section in prompt templates.

### 17. From Haystack — Statement decomposition in evaluators

Their pattern of breaking output into atomic claims and scoring each independently produces more granular evidence than a single holistic verdict. For evaluators like `cooperation` or `instruction_adherence`, decomposing agent behavior into individual observable claims before scoring would reduce judgment variance and make evaluation results more interpretable.

### 18. From Haystack — Cross-run comparison reports

Their `comparative_detailed_report()` produces side-by-side metric diffs across evaluation runs. A `RunComparison` model that takes two `EvaluationReport` objects and produces per-metric deltas would be useful for iterating on scenario design, comparing models, and measuring the effect of prompt changes.