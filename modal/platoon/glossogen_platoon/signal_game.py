"""The module a training config's ``package`` names: importing it registers the signal_game harness
(``glossogen-signal-game``), its episode program (``glossogen-signal-game``) and its credit
estimator (``glossogen-round-baseline``) with platoon."""

from glossogen_platoon import credit, harness, program

REGISTERED = (credit.ESTIMATOR_NAME, harness.HARNESS_NAME, program.PROGRAM_NAME)
