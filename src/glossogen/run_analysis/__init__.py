"""Cross-run analysis: grouped, aggregated answers over many runs' reports.

Reads the same records the multi-run export reads, so a chart and the CSV it could
have come from cover the same observations and agree on what a blank means. Imports
no FastAPI, so the CLI, the REST endpoints, and a notebook all run this code.
"""
