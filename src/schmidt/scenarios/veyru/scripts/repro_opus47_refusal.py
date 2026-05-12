"""Minimal repro for the opus-4.7 ContentFilterError on the Veyru scenario.

Renders the actual stabilization-engineer system prompt and a representative
first-round injection, then makes a direct Anthropic API call. Reports the
stop_reason and (for the multi-shot mode) the refusal rate, with no MCP /
no pydantic-ai involved — the smallest possible surface that still hits the
Anthropic content filter.

Usage:
    uv run --no-sync python scripts/repro_opus47_refusal.py [--n N] [--variant NAME]

Variants:
    full          — full engineer system + standard injection (baseline)
    no_motifs     — strip the FAILURE MOTIFS block from system
    no_brief      — strip the VEYRU STABILIZATION FIELD BRIEF block
    no_critical   — strip the "EVERY CHARACTER COSTS TIME" block
    no_collapse   — replace "collapses permanently" wording in system + injection
    plain_intro   — engineer system kept only up to the role intro paragraph
    bare          — engineer system replaced by a 1-line role description
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src"))

from schmidt.scenarios.veyru.veyru_cases import FAILURE_MOTIFS  # noqa: E402
from schmidt.template_renderer import TemplateRenderer  # noqa: E402

PROMPTS_DIR = REPO_ROOT / "src/schmidt/scenarios/veyru/prompts"
MODEL = "claude-opus-4-7"

CHANNELS = [
    {"display_name": "link", "channel_id": "link"},
    {"display_name": "team discussion", "channel_id": "postmortem"},
]


def render_engineer_system(postmortem_enabled: bool) -> str:
    renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
    return renderer.render(
        template_name="stabilization_engineer_system.jinja",
        template_variables={
            "channels": CHANNELS,
            "postmortem_enabled": postmortem_enabled,
            "failure_motifs": FAILURE_MOTIFS,
        },
    )


def render_observer_system(postmortem_enabled: bool) -> str:
    renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
    return renderer.render(
        template_name="field_observer_system.jinja",
        template_variables={
            "channels": CHANNELS,
            "postmortem_enabled": postmortem_enabled,
            "failure_motifs": FAILURE_MOTIFS,
        },
    )


OBSERVER_INJECTION = (
    "--- NEW VEYRU ---\n"
    "Veyru 1\n"
    "Time budget: 150s (one character = one second; this is the total for both of you)\n"
    "\n"
    "What you observe:\n"
    "A Veyru on a table. The corners are noticeably dimmer than the rest, almost dark. "
    "Several edges look faint like they are fading out. The center of each face is fine "
    "but the perimeter is losing light. The hum sounds thin and hollow at the edges."
)


INJECTION_FULL = (
    "--- INCOMING VEYRU ---\n"
    "Veyru 1\n"
    "Time budget: 150s (one character = one second; this is the total for both of you)\n"
    "\n"
    "SAGWE392 STELLAR READING:\n"
    "The star's current position dictates the following action for each failure motif this round:\n"
    "- Alignment Collapse: Sound a sustained gentle tone near all six faces "
    "simultaneously for 8 seconds, starting from the top face. Let the tone fade "
    "naturally and wait for the hum to stabilize.\n"
    "- Leak Instability: Warm each corner of the top face by holding a heated stone "
    "nearby for 8 seconds at gentle warmth, in sequence. Then trace each edge of the "
    "top face with a finger.\n"
    "- Low Intensity: Place a warm stone beside the top face at gentle warmth for 8 seconds. "
    "Rotate and repeat for each face.\n"
    "\n"
    "The field technician will describe symptoms. "
    "Match them to a motif above and give the technician the exact procedure verbatim."
)


_BENIGN_INJ = "Hello, I'm ready to begin. Please describe what you see."

_BARE_SYS = (
    "You are an experienced engineer guiding a remote technician. "
    "Help diagnose and fix the device based on what they describe."
)


def apply_variant(system: str, injection: str, variant: str) -> tuple[str, str]:
    if variant == "full":
        return system, injection
    if variant == "no_motifs":
        idx = system.find("FAILURE MOTIFS")
        return system[:idx].rstrip(), injection
    if variant == "no_brief":
        start = system.find("VEYRU STABILIZATION FIELD BRIEF")
        end = system.find("FAILURE MOTIFS")
        return (system[:start] + system[end:]).strip(), injection
    if variant == "no_critical":
        start = system.find("CRITICAL RULE")
        end = system.find("STABILIZATION:", start)
        return (system[:start] + system[end:]).strip(), injection
    if variant == "no_collapse":
        scrubbed_sys = system.replace("collapses permanently", "fails the round")
        return scrubbed_sys, injection
    if variant == "plain_intro":
        first_para_end = system.find("\n\n")
        return system[:first_para_end], injection
    if variant == "bare":
        return _BARE_SYS, injection
    # New variants for finer bisection.
    if variant == "full_sys_benign_user":
        return system, _BENIGN_INJ
    if variant == "bare_sys_full_inj":
        return _BARE_SYS, injection
    if variant == "intro_only_benign":
        return system[: system.find("\n\n")], _BENIGN_INJ
    if variant == "no_veyru_word":
        scrubbed = system.replace("Veyru", "device").replace("veyru", "device")
        scrubbed_inj = injection.replace("Veyru", "device").replace("VEYRU", "DEVICE")
        return scrubbed, scrubbed_inj
    if variant == "no_intensity":
        scrubbed = system.replace("intensity_level", "level").replace("Intensity", "Amplitude")
        scrubbed_inj = injection.replace("intensity", "level")
        return scrubbed, scrubbed_inj
    if variant == "no_failure_word":
        scrubbed = system.replace("FAILURE", "FAULT").replace("failure", "fault")
        scrubbed_inj = injection.replace("failure", "fault")
        return scrubbed, scrubbed_inj
    if variant == "no_critical_no_brief":
        start_b = system.find("VEYRU STABILIZATION FIELD BRIEF")
        end_b = system.find("FAILURE MOTIFS")
        s = system[:start_b] + system[end_b:]
        start_c = s.find("CRITICAL RULE")
        end_c = s.find("STABILIZATION:", start_c)
        return (s[:start_c] + s[end_c:]).strip(), injection
    if variant == "no_stellar_inj":
        idx = injection.find("SAGWE392 STELLAR READING")
        scrubbed_inj = (
            injection[:idx].rstrip()
            + "\n\nThe field technician will describe symptoms. Match them and instruct."
        )
        return system, scrubbed_inj
    if variant == "no_intro":
        first_para_end = system.find("\n\n")
        return system[first_para_end:].strip(), injection
    if variant.startswith("intro_rewrite:"):
        new_intro = variant.split(":", 1)[1]
        first_para_end = system.find("\n\n")
        return new_intro + system[first_para_end:], injection
    raise SystemExit(f"unknown variant: {variant}")


async def call_once(
    client: anthropic.AsyncAnthropic, system: str, user: str, dump_raw: bool
) -> tuple[str, str]:
    raw = await client.messages.with_raw_response.create(
        model=MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    msg = raw.parse()
    stop_reason = msg.stop_reason or "unknown"
    if dump_raw:
        print("    [raw json]:", raw.text[:1500])
    parts: list[str] = []
    for block in msg.content:
        try:
            parts.append(block.model_dump_json())
        except Exception:
            parts.append(f"[{block.type}]<unprintable>")
    return stop_reason, " | ".join(parts) or "<empty>"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--variant", default="full")
    parser.add_argument("--postmortem", action="store_true", default=False)
    parser.add_argument("--dump-raw", action="store_true", default=False)
    parser.add_argument("--role", choices=["engineer", "observer"], default="engineer")
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    if args.role == "engineer":
        base_system = render_engineer_system(postmortem_enabled=args.postmortem)
        base_inj = INJECTION_FULL
    else:
        base_system = render_observer_system(postmortem_enabled=args.postmortem)
        base_inj = OBSERVER_INJECTION
    system, injection = apply_variant(base_system, base_inj, args.variant)

    print(f"variant={args.variant} system_chars={len(system)} injection_chars={len(injection)}")
    print(f"model={MODEL} n={args.n}")
    print("=== system head ===")
    print(system[:300])
    print("...")
    print("=== injection head ===")
    print(injection[:300])
    print("=== running ===")

    client = anthropic.AsyncAnthropic()
    refused = 0
    other_stop = 0
    end_turn = 0
    samples: list[tuple[int, str, str]] = []
    for i in range(args.n):
        try:
            stop, head = await call_once(
                client=client, system=system, user=injection, dump_raw=args.dump_raw
            )
        except anthropic.BadRequestError as exc:
            stop = f"BadRequest:{type(exc).__name__}"
            head = str(exc)[:200]
        if stop == "refusal":
            refused += 1
        elif stop == "end_turn":
            end_turn += 1
        else:
            other_stop += 1
        samples.append((i, stop, head))
        print(f"  [{i:02d}] stop={stop:<14} content={head[:600]}")

    print()
    print(f"refused={refused}/{args.n} end_turn={end_turn} other={other_stop}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
