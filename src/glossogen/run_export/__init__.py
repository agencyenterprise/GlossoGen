"""Exporting many runs at once, as raw run folders or as CSV tables.

Nothing here imports FastAPI, so the same code answers a REST request and a
`glossogen export` invocation that never starts a server. The wire models are
also the builders' input models, so there is no translation layer between what a
client asks for and what gets built.

The CSV side is scenario-agnostic by construction: knob columns come from the
`scenario_config` a run recorded, and evaluator columns come from the metric
names its report actually carries. Neither is a list anyone maintains, so adding
a scenario or a metric needs no change here.
"""
