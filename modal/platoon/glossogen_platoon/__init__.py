"""signal_game as a platoon environment: the root harness, the episode program and the per-round
credit estimator.

A training config names ``package: glossogen_platoon.signal_game``, whose import registers the
three. This package's ``__init__`` imports nothing, so that GlossoGen's environment can import
``glossogen_platoon.game_scores`` without platoon.
"""
