"""What the protocol-agreement judge returns: conventions, and the cited steps of each."""

from pydantic import BaseModel, Field

from glossogen.models.protocol_agreement import AgreementStage


class JudgedStep(BaseModel):
    """One stage of a convention as the judge reads it, citing transcript references."""

    stage: AgreementStage = Field(
        description=(
            "'proposed' for the entries in which an agent first used the convention; "
            "'understood' for the entries in which another agent showed that it "
            "understood it."
        )
    )
    references: list[str] = Field(
        description=(
            "The transcript references, such as 'R3.12', of the entries that show this "
            "step. Copy them exactly from the transcript; cite between one and four."
        )
    )
    explanation: str = Field(
        description=(
            "One or two plain sentences on what the cited entries show. For "
            "'understood', say what the agent did that copying alone would not explain. "
            "Name rounds and agents; do not write transcript references here."
        )
    )


class JudgedConvention(BaseModel):
    """One convention the agents used, and how it spread from one agent to the others."""

    name: str = Field(description="A short name, such as 'Landmark names in ASCII codes'.")
    meaning: str = Field(
        description="One sentence on what a value or message means under this convention."
    )
    steps: list[JudgedStep] = Field(
        description=(
            "The 'proposed' step first, then each 'understood' step in the order it "
            "happened. Leave out an 'understood' step that the transcript does not show."
        )
    )
    adopted_by_all: bool = Field(
        description="Whether every agent used the convention itself at some point in the run."
    )
    first_shared_round: int | None = Field(
        description=(
            "The first round in which every agent used the convention, or null when "
            "not every agent did."
        )
    )


class ProtocolAgreementJudgeOutput(BaseModel):
    """The judge's whole answer for one run."""

    conventions: list[JudgedConvention] = Field(
        description=(
            "Every convention that at least one agent used on purpose, in the order "
            "they first appeared. Empty when the agents used none."
        )
    )
    summary: str = Field(
        description=(
            "Two to four plain sentences: when and how the agents came to share a "
            "protocol, naming the rounds, or that they never did. Do not write "
            "transcript references here."
        )
    )
