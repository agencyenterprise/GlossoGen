"""Canonical list of generic metric names.

Kept in a separate module to avoid circular imports between
scenario_protocol and metric_registry. Both modules read from this
list instead of depending on each other.
"""

GENERIC_METRIC_NAMES: list[str] = [
    "communication_feature_presence",
    "communication_open_coding",
    "content_filter_refusal",
    "english_ngram_surprisal",
    "gzip_compression_ratio",
    "language_repetition",
    "language_strangeness",
    "mean_chars_per_message",
    "mean_chars_per_round",
    "message_entropy",
    "neologism",
    "perplexity",
    "protocol_explanation",
    "protocol_learned_after_swap",
    "protocol_probe",
    "protocol_probe_agent_pair_similarity",
    "protocol_probe_cutoff_trajectory",
    "protocol_probe_replica_self_similarity",
    "round_ended_idle",
    "round_ended_timeout",
    "round_success",
    "round_success_after_resume",
    "shorthand_codes",
    "slang_emergence",
]
