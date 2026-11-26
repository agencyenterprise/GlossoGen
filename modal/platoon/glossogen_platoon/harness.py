"""``harness: glossogen-signal-game``: the root agent of an episode, which plays one signal_game
game.

The root makes no model call itself. For each seat that platoon serves, it mints a platoon agent
with the seat's name as its role (``POST /v1/platoon/agents``), so the seat's calls land on a
trajectory of their own and sample the policy that ``agents.roles`` binds to that role. It then runs
``glossogen run`` with each such seat's model name mapped to its agent's URL. A seat named in
``external_seats`` plays a model outside platoon instead, which platoon neither records nor trains.
When the game ends, the GlossoGen-side scorer writes the game's labels and reads its scores, and the
harness records them on the root as ``misc["glossogen"]`` (a ``PlayedGame``).

The harness options:

- ``game_config``: the signal_game config; platoon makes a relative path absolute against the
  training config's folder;
- ``runs_dir``: where GlossoGen writes the games' run directories, relative to the working directory
  or absolute;
- ``labels``: the labels of each game, besides ``seed=<seed>`` and ``task=<task id>``;
- ``external_seats``: ``{seat: {model, provider, base_url}}``, the seats that play a model outside
  platoon; a ``self-hosted`` one needs a ``base_url``, and ``SELF_HOSTED_API_KEY`` in the
  environment;
- ``max_agent_turns``: GlossoGen's ``--max-agent-turns``.
"""

from pathlib import Path
from typing import NamedTuple

import aiohttp
import platoon as pt
from glossogen_platoon.game_process import (
    SELF_HOSTED,
    GameSettings,
    SeatModel,
    play_game,
    score_game,
)
from glossogen_platoon.game_scores import PlayedGame
from pydantic import BaseModel, ConfigDict

HARNESS_NAME = "glossogen-signal-game"
SEATS = ("player_a", "player_b")
MINTED_STATUS = 201


class ExternalSeat(BaseModel):
    """A seat that plays a model outside platoon."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str
    base_url: str | None


class HarnessOptions(BaseModel):
    """The harness's options (the module's docstring)."""

    model_config = ConfigDict(extra="forbid")

    game_config: Path
    runs_dir: Path
    labels: list[str]
    external_seats: dict[str, ExternalSeat]
    max_agent_turns: int


class MintedAgent(BaseModel):
    """What the gateway answers when it mints an agent."""

    model_config = ConfigDict(extra="allow")

    agent_id: str
    base_url: str


async def mint_agent(*, endpoint: pt.ModelEndpoint, role: str) -> MintedAgent:
    """A new platoon agent of ``role`` under the root agent's endpoint."""
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{endpoint.base_url}/platoon/agents", json={"role": role}) as reply:
            if reply.status != MINTED_STATUS:
                raise RuntimeError(f"minting {role} failed: {reply.status} {await reply.text()}")
            return MintedAgent.model_validate(await reply.json())


def external_model(*, seat: ExternalSeat) -> SeatModel:
    """The model of a seat outside platoon."""
    return SeatModel(model=seat.model, provider=seat.provider, base_url=seat.base_url)


class SeatPlan(NamedTuple):
    """Each seat's model, and the platoon agent of each seat that platoon serves."""

    models: dict[str, SeatModel]
    agents: dict[str, str]


async def plan_seats(*, endpoint: pt.ModelEndpoint, options: HarnessOptions) -> SeatPlan:
    """Mint an agent for each seat that platoon serves, and name every seat's model."""
    unknown = sorted(set(options.external_seats) - set(SEATS))
    if unknown:
        raise ValueError(f"external_seats names seats that signal_game does not have: {unknown}")
    models: dict[str, SeatModel] = {}
    agents: dict[str, str] = {}
    for seat in SEATS:
        if seat in options.external_seats:
            models[seat] = external_model(seat=options.external_seats[seat])
            continue
        agent = await mint_agent(endpoint=endpoint, role=seat)
        models[seat] = SeatModel(
            model=f"seat-{seat}", provider=SELF_HOSTED, base_url=agent.base_url
        )
        agents[seat] = agent.agent_id
    return SeatPlan(models=models, agents=agents)


@pt.harness(HARNESS_NAME, path_options=("game_config",))
async def signal_game_root(ctx: pt.AgentContext) -> pt.AgentResult:
    """Mint the platoon seats' agents, play one game, and record its scores on the root."""
    options = HarnessOptions.model_validate(dict(ctx.options))
    seed = int(ctx.task.misc["seed"])
    plan = await plan_seats(endpoint=ctx.endpoint, options=options)
    external_self_hosted = any(
        seat.provider == SELF_HOSTED for seat in options.external_seats.values()
    )
    settings = GameSettings(
        game_config=options.game_config.resolve(),
        runs_dir=options.runs_dir.resolve(),
        max_agent_turns=options.max_agent_turns,
    )
    run_id = await play_game(
        settings=settings, seed=seed, seats=plan.models, external_self_hosted=external_self_hosted
    )
    labels = [*options.labels, f"seed={seed}", f"task={ctx.task.id}"]
    scores = await score_game(run_dir=settings.runs_dir / run_id, labels=labels)
    game = PlayedGame(run_id=run_id, seed=seed, seat_agents=plan.agents, scores=scores)
    ctx.annotate(glossogen=game.model_dump(mode="json"))
    return pt.AgentResult(status="completed", final_message=f"run {run_id}")
