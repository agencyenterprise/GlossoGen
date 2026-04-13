"""Configuration knobs for the emergency room scenario.

Controls the simulated time cost of communication: each word in a
send_message call costs ``seconds_per_token`` simulated seconds. Patients
die if cumulative radio time exceeds their time budget.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class EmergencyRoomKnobs(BaseKnobs):
    """Configuration knobs for the emergency room scenario.

    ``seconds_per_token`` controls how many simulated seconds each word
    costs when agents communicate. ``judge_model`` and ``judge_provider``
    specify the LLM used to evaluate whether treatment actions match
    the patient's critical needs.
    """

    seconds_per_token: float
    judge_model: str
    judge_provider: str
