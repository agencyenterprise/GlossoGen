"""Print everything the replaced agent received on resume.

For a replace-agent run, three streams shape the new agent's first
``agent.run()`` call:

1. The pydantic-ai system prompt configured on the ``Agent`` instance
   (rendered from the *new* scenario knobs — so e.g. the discussion-phase
   section is gone when ``postmortem_disabled_at_start=True``).
2. The reconstructed message history passed as ``message_history`` —
   built by ``build_message_history`` with ``tool_calls_only=True`` and
   ``blocked_channel_ids=<postmortem set>`` for the replaced agent.
3. The round injection delivered via the first ``read_notifications``
   call after resume (the world's standard mechanism for handing off
   per-round context).

This script reproduces (1) by reading the post-resume ``AgentRegistered``
event, (2) by re-running ``build_rewind_state_from_last_message`` with
the manifest's filter, and (3) by reading the post-resume
``InjectionDelivered`` event for the replaced agent's first round.
"""

import argparse
import asyncio
import json
from pathlib import Path

from schmidt.cli import _read_replace_manifest
from schmidt.evaluation.log_reader import load_events
from schmidt.message_rewind import AgentHistoryFilter, build_rewind_state_from_last_message
from schmidt.models.event import AgentRegistered, InjectionDelivered


def _print_section(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * 8}\n")


def _format_part(part: object) -> str:
    """Render a single ModelMessage part with a short prefix tag."""
    cls = type(part).__name__
    if cls == "SystemPromptPart":
        return f"SYSTEM:\n{getattr(part, 'content', '')}"
    if cls == "UserPromptPart":
        return f"USER: {getattr(part, 'content', '')}"
    if cls == "TextPart":
        return f"TEXT: {getattr(part, 'content', '')}"
    if cls == "ThinkingPart":
        return f"THINKING: {getattr(part, 'content', '')}"
    if cls == "ToolCallPart":
        args_obj = getattr(part, "args", "")
        args_str = json.dumps(args_obj) if not isinstance(args_obj, str) else args_obj
        return f"TOOL_CALL {getattr(part, 'tool_name', '?')}({args_str})"
    if cls == "ToolReturnPart":
        content = getattr(part, "content", "")
        return f"TOOL_RETURN {getattr(part, 'tool_name', '?')} -> {content}"
    return cls


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Replace-agent run directory")
    parser.add_argument(
        "--scenario",
        type=str,
        default="veyru",
        help="Scenario name (default: veyru)",
    )
    parser.add_argument(
        "--max-history-parts",
        type=int,
        default=400,
        help="Cap how many history parts to print (default: 400)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    log_path = run_dir / f"{args.scenario}.jsonl"

    replace_info = _read_replace_manifest(run_dir=run_dir)
    if replace_info is None:
        raise SystemExit(f"No replace_manifest.json in {run_dir}")
    replaced = replace_info.replaced_agent_id

    events = await load_events(log_path=log_path)

    # 1. System prompt — read from the post-resume AgentRegistered event
    regs = [
        event
        for event in events
        if isinstance(event, AgentRegistered) and event.agent_id == replaced
    ]
    if not regs:
        raise SystemExit(f"No AgentRegistered event for {replaced}")
    new_reg = regs[-1]
    _print_section(f"SYSTEM PROMPT delivered to {replaced}")
    print(new_reg.system_prompt)

    # 2. Reconstructed pydantic-ai history — replay build_rewind_state with the filter
    agent_filters = {
        replaced: AgentHistoryFilter(
            tool_calls_only=True,
            channel_visibility=replace_info.channel_visibility,
            imported=None,
        )
    }
    state = build_rewind_state_from_last_message(events=events, agent_filters=agent_filters)
    history = state.agent_message_histories[replaced]
    _print_section(
        f"PYDANTIC-AI MESSAGE_HISTORY for {replaced} ({len(history)} ModelMessage entries)"
    )
    parts_printed = 0
    for index, message in enumerate(history):
        message_cls = type(message).__name__
        for part in message.parts:
            if parts_printed >= args.max_history_parts:
                print(f"... truncated at {args.max_history_parts} parts")
                break
            print(f"[{index:03d} {message_cls}] {_format_part(part=part)}")
            parts_printed += 1
        if parts_printed >= args.max_history_parts:
            break

    # 3. Post-resume round injections — every InjectionDelivered whose timestamp
    #    is at or after the manifest's replaced_at moment.
    replaced_at = run_dir / "replace_manifest.json"
    manifest = json.loads(replaced_at.read_text())
    boundary = float(manifest["replaced_at"])
    post_resume_injections = [
        event
        for event in events
        if isinstance(event, InjectionDelivered)
        and event.agent_id == replaced
        and event.timestamp.timestamp() >= boundary
    ]
    for injection in post_resume_injections:
        _print_section(
            f"POST-RESUME ROUND INJECTION for {replaced} (round {injection.round_number})"
        )
        print(injection.text)


if __name__ == "__main__":
    asyncio.run(main())
