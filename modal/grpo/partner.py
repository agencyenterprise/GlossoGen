"""The frozen partner: a model that plays one seat of every game and does not train.

A partner file is a JSON object with three keys:

- ``seat``: the agent id of the seat that the partner plays, such as ``player_b``;
- ``model_override``: that seat's entry in GlossoGen's ``model_overrides`` knob, with
  ``model``, ``provider`` and ``model_settings``;
- ``base_url``: the ``/v1`` URL of a self-hosted partner that the policy server does not serve,
  and null for every other partner.

A self-hosted partner named BASE_MODEL plays on the policy server, which serves the base model
under that name beside the adapters. A partner with no provider is self-hosted, because the loop
plays every game under ``--provider self-hosted``. Without ``model_settings``, the partner sends
the game config's ``agent_model_settings``, which hold vLLM's sampling options, so a partner on
another provider names its own.
"""

import re
from pathlib import Path
from typing import Self

from grpo_records import BASE_MODEL
from pydantic import BaseModel, ConfigDict, model_validator

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.scenario_contract.base_knobs import AgentModelOverride


class Partner(BaseModel):
    """The seat that a model which does not train plays, and that model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seat: str
    model_override: AgentModelOverride
    base_url: str | None

    @model_validator(mode="after")
    def _self_hosted_partner_has_a_server(self) -> Self:
        """A self-hosted partner other than the base model names its server, and no other does."""
        on_policy_server = self.self_hosted() and self.model_override.model == BASE_MODEL
        needs_url = self.self_hosted() and not on_policy_server
        if needs_url and self.base_url is None:
            raise ValueError(
                f"the self-hosted partner {self.model_override.model} needs a base_url; "
                f"only {BASE_MODEL} plays on the policy server"
            )
        if not needs_url and self.base_url is not None:
            raise ValueError("base_url is only for a self-hosted partner other than the base model")
        return self

    def self_hosted(self) -> bool:
        """Whether the partner plays under the ``self-hosted`` provider."""
        provider = self.model_override.provider
        return provider is None or provider == Provider.SELF_HOSTED

    def label(self) -> str:
        """The partner in a form fit for a file name: its seat and its model."""
        return re.sub(r"[^A-Za-z0-9._]+", "-", f"{self.seat}-{self.model_override.model}")


def load_partner(*, path: Path) -> Partner:
    """Read and validate a partner file."""
    return Partner.model_validate_json(path.read_text())


def self_hosted_urls(*, policy_model: str, url: str, partner: Partner | None) -> dict[str, str]:
    """``SELF_HOSTED_BASE_URLS`` for a game: the policy and a self-hosted partner."""
    urls = {policy_model: url}
    if partner is None or not partner.self_hosted():
        return urls
    if partner.base_url is None:
        urls[partner.model_override.model] = url
    else:
        urls[partner.model_override.model] = partner.base_url
    return urls


def trained_seats(*, players: tuple[str, ...], partner: Partner | None) -> tuple[str, ...]:
    """The seats whose answers train: every seat but the partner's."""
    if partner is None:
        return players
    return tuple(player for player in players if player != partner.seat)


def partner_labels(*, partner: Partner | None) -> list[str]:
    """The run labels that name a game's partner, or none without one."""
    if partner is None:
        return []
    return [f"partner_seat={partner.seat}", f"partner={partner.model_override.model}"]
