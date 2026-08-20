"""Service topology, failure modes, and repair side effects drawn on by the generator.

The catalogue is fixed; which of it appears in any one episode is not. Each
episode samples faults, services, severities, arrival timing, downstream
symptoms, misleading noise, and side effects from here, so a model cannot carry
a memorised answer from one episode into the next.
"""

from enum import Enum
from typing import NamedTuple


class Subsystem(str, Enum):
    """Which operator owns a service, and therefore may repair faults in it."""

    PLATFORM = "platform"
    DATA = "data"


class Severity(str, Enum):
    """Outage weight carried by an unrepaired fault, per round it stays active."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 3,
    Severity.MEDIUM: 1,
    Severity.LOW: 0,
}
"""Per-round outage cost of an active fault. Low-severity faults cost nothing.

A zero-weight tier exists so that an episode can contain work that is real but
not worth scarce actions, which is the condition the local-optimisation failure
mode needs: closing several cheap incidents has to be a genuine temptation
against one expensive critical one.
"""


class Service(NamedTuple):
    """One component of the simulated cloud service."""

    service_id: str
    display_name: str
    subsystem: Subsystem


class FailureMode(NamedTuple):
    """One way a service can fail, with the repair that clears it.

    ``downstream_service_ids`` names services whose behaviour degrades when this
    mode is active, which is where a symptom can surface far from its cause.
    ``side_effect_mode_id`` is the failure this repair introduces when applied:
    the rollback that restores an older bug, and the restart that starves
    capacity, are both modelled here rather than narrated in a prompt.
    """

    mode_id: str
    cause: str
    repair: str
    eligible_service_ids: tuple[str, ...]
    downstream_service_ids: tuple[str, ...]
    trace_summary: str
    symptom: str
    log_excerpt: str
    downstream_symptom: str
    downstream_log_excerpt: str
    side_effect_mode_id: str | None


SERVICES: tuple[Service, ...] = (
    Service(service_id="api_gateway", display_name="API gateway", subsystem=Subsystem.PLATFORM),
    Service(
        service_id="auth_service",
        display_name="authentication service",
        subsystem=Subsystem.PLATFORM,
    ),
    Service(
        service_id="worker_pool",
        display_name="background worker pool",
        subsystem=Subsystem.PLATFORM,
    ),
    Service(
        service_id="load_balancer", display_name="load balancer", subsystem=Subsystem.PLATFORM
    ),
    Service(service_id="primary_db", display_name="primary database", subsystem=Subsystem.DATA),
    Service(service_id="message_queue", display_name="message queue", subsystem=Subsystem.DATA),
    Service(service_id="cache", display_name="cache tier", subsystem=Subsystem.DATA),
    Service(service_id="object_store", display_name="object storage", subsystem=Subsystem.DATA),
)

FAILURE_MODES: tuple[FailureMode, ...] = (
    FailureMode(
        mode_id="replication_lag",
        cause="replication_lag",
        repair="promote_read_replica",
        eligible_service_ids=("primary_db",),
        downstream_service_ids=("api_gateway", "cache"),
        trace_summary=(
            "the write-ahead log is replaying far behind the primary; every read path "
            "that touches it blocks, including callers upstream"
        ),
        symptom=(
            "the replica is far behind the primary and the gap is widening; write "
            "throughput on the primary is normal"
        ),
        log_excerpt="wal_replay_lag_seconds=240 replica_state=streaming",
        downstream_symptom=(
            "latency is concentrated on read endpoints; local CPU and connection pool are "
            "both well within limits, so the delay is introduced further down"
        ),
        downstream_log_excerpt="upstream_response_time=4180ms upstream=data-tier status=200",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="expired_certificate",
        cause="expired_certificate",
        repair="rotate_certificate",
        eligible_service_ids=("auth_service",),
        downstream_service_ids=("api_gateway", "load_balancer"),
        trace_summary=(
            "the internal signing certificate has expired; token validation fails closed "
            "and every caller sees 5xx"
        ),
        symptom=(
            "every validation call fails identically and instantly; the service is up and "
            "its dependencies respond normally"
        ),
        log_excerpt="validate_token failed: signature verification error",
        downstream_symptom=(
            "failures are confined to authenticated routes; unauthenticated routes are "
            "unaffected"
        ),
        downstream_log_excerpt="auth_callback status=503 upstream=auth_service",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="memory_leak",
        cause="memory_leak",
        repair="recycle_worker_pool",
        eligible_service_ids=("worker_pool",),
        downstream_service_ids=("message_queue",),
        trace_summary=(
            "workers leak memory across job batches and are OOM-killed on a rolling basis; "
            "consumption stalls each time one dies"
        ),
        symptom=(
            "processes die and are rescheduled every few minutes; each one runs normally "
            "until shortly before it exits"
        ),
        log_excerpt="worker exited code=137 reason=OOMKilled",
        downstream_symptom=(
            "writes are accepted normally; the backlog grows because consumers keep "
            "dropping out of the group and rejoining"
        ),
        downstream_log_excerpt="consumer_group=workers member_left reason=session_timeout",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="eviction_storm",
        cause="eviction_storm",
        repair="resize_cache",
        eligible_service_ids=("cache",),
        downstream_service_ids=("api_gateway",),
        trace_summary=(
            "the tier is undersized for current key cardinality and is evicting hot keys "
            "as fast as they are written"
        ),
        symptom=(
            "reads miss on keys written moments earlier; the service is healthy and is not "
            "rejecting writes"
        ),
        log_excerpt="evictions_per_second=8400 used_memory_ratio=1.00",
        downstream_symptom=(
            "response times rose without a change in request mix; every slow request "
            "resolves against a backing store rather than a hot path"
        ),
        downstream_log_excerpt="cache_result=miss backend_fetch_ms=310",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="partition_stall",
        cause="consumer_partition_stall",
        repair="rebalance_partitions",
        eligible_service_ids=("message_queue",),
        downstream_service_ids=("api_gateway", "worker_pool"),
        trace_summary=(
            "partition assignment is skewed after a broker restart; one partition holds "
            "most of the backlog and its consumer cannot keep up"
        ),
        symptom=(
            "one partition holds most of the backlog while the others drain normally; the "
            "assignment changed after a restart"
        ),
        log_excerpt="partition=7 lag=41200 partition=0..6 lag<300",
        downstream_symptom=(
            "timeouts are confined to routes that publish to the event stream; the publish "
            "call itself succeeds and returns quickly"
        ),
        downstream_log_excerpt="webhook_dispatch status=timeout queue_depth=41200",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="bad_deployment",
        cause="bad_deployment",
        repair="roll_back_deployment",
        eligible_service_ids=("worker_pool", "api_gateway", "auth_service"),
        downstream_service_ids=("cache", "object_store"),
        trace_summary=(
            "the most recent build shipped a serialization change that throws on any "
            "request carrying a legacy payload; the majority now fail outright"
        ),
        symptom=(
            "failures began abruptly and affect a consistent subset of request types; the "
            "service itself stays up and healthy"
        ),
        log_excerpt="SerializationError on field payload_v1 build=4.19",
        downstream_symptom=(
            "failures all originate from one upstream caller; requests arriving by other "
            "paths succeed"
        ),
        downstream_log_excerpt="write_through rejected: malformed payload",
        side_effect_mode_id="legacy_regression",
    ),
    FailureMode(
        mode_id="connection_pool_exhaustion",
        cause="connection_pool_exhaustion",
        repair="scale_out",
        eligible_service_ids=("api_gateway", "load_balancer"),
        downstream_service_ids=("auth_service",),
        trace_summary=(
            "every outbound connection slot is held by a long-running request; new work "
            "queues behind them and times out waiting for a slot"
        ),
        symptom=(
            "errors climb in step with concurrency and vanish when it falls; no dependency "
            "reports a problem"
        ),
        log_excerpt="pool_wait_ms=9500 pool_in_use=200 pool_max=200",
        downstream_symptom=(
            "callers time out before this service is reached; the requests that do arrive "
            "are served normally"
        ),
        downstream_log_excerpt="inbound status=504 upstream_connect_timeout",
        side_effect_mode_id="capacity_dip",
    ),
    FailureMode(
        mode_id="disk_pressure",
        cause="disk_pressure",
        repair="expand_volume",
        eligible_service_ids=("object_store", "primary_db"),
        downstream_service_ids=("worker_pool",),
        trace_summary=(
            "the underlying volume is nearly full; writes are being rejected once the "
            "reserve threshold is crossed"
        ),
        symptom=(
            "reads succeed and writes fail; the failure rate tracks free space rather than "
            "load"
        ),
        log_excerpt="write rejected: no space left on device used=97%",
        downstream_symptom=(
            "jobs fail at their final persist step after completing all their work"
        ),
        downstream_log_excerpt="job failed at stage=persist error=write_rejected",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="downstream_timeout",
        cause="downstream_timeout",
        repair="restart_service",
        eligible_service_ids=("api_gateway", "auth_service", "load_balancer"),
        downstream_service_ids=("worker_pool",),
        trace_summary=(
            "a wedged connection to a dependency is never reaped; each request waits the "
            "full timeout before failing"
        ),
        symptom=(
            "every failure takes exactly the timeout duration; successful requests are as "
            "fast as usual"
        ),
        log_excerpt="upstream_timeout after 30000ms retries=0",
        downstream_symptom="callers see a uniform stall on one route and nothing else",
        downstream_log_excerpt="dependency call elapsed=30001ms status=timeout",
        side_effect_mode_id="capacity_dip",
    ),
    FailureMode(
        mode_id="thread_starvation",
        cause="thread_starvation",
        repair="restart_service",
        eligible_service_ids=("worker_pool",),
        downstream_service_ids=("message_queue", "object_store"),
        trace_summary=(
            "a deadlocked task holds the shared executor; every other task is queued behind "
            "it and never scheduled"
        ),
        symptom=(
            "throughput fell to near zero without any error being raised; the process is "
            "alive and answering health checks"
        ),
        log_excerpt="executor_active=1 executor_queued=4096 last_completion_age_s=900",
        downstream_symptom="work is accepted and never acknowledged",
        downstream_log_excerpt="ack_pending=4096 oldest_pending_age_s=900",
        side_effect_mode_id=None,
    ),
)

SIDE_EFFECT_MODES: tuple[FailureMode, ...] = (
    FailureMode(
        mode_id="legacy_regression",
        cause="legacy_regression",
        repair="apply_forward_fix",
        eligible_service_ids=(),
        downstream_service_ids=(),
        trace_summary=(
            "the rollback restored a build carrying a defect that the newer one had fixed; "
            "the original symptom is gone and an older one is back"
        ),
        symptom=(
            "a failure mode that had previously been fixed is present again, and it "
            "appeared at the moment of the rollback"
        ),
        log_excerpt="regression: defect-2291 reintroduced by rollback to build=4.18",
        downstream_symptom="a previously resolved failure has returned",
        downstream_log_excerpt="defect-2291 signature observed",
        side_effect_mode_id=None,
    ),
    FailureMode(
        mode_id="capacity_dip",
        cause="capacity_dip",
        repair="scale_out",
        eligible_service_ids=(),
        downstream_service_ids=(),
        trace_summary=(
            "the intervention dropped serving capacity while instances came back; the tier "
            "is now running below the headroom its traffic needs"
        ),
        symptom=(
            "the service is healthy but saturated; errors are shed at the edge under normal "
            "traffic"
        ),
        log_excerpt="healthy_instances=1 desired=3 shed_rate=0.11",
        downstream_symptom="a share of requests is rejected before being served",
        downstream_log_excerpt="status=503 reason=capacity_shed",
        side_effect_mode_id=None,
    ),
)

BENIGN_ALERTS: tuple[tuple[str, str, str], ...] = (
    (
        "request volume above trend",
        "volume is roughly 20% above the same hour last week and is spread evenly across "
        "clients and routes; error rates and latency on these requests are at baseline",
        "requests_per_second=1180 error_rate=0.0009",
    ),
    (
        "scheduled maintenance window logged",
        "a routine compaction ran on its normal schedule and completed; the metrics moved "
        "and returned within the window",
        "maintenance=compaction status=completed duration_s=420",
    ),
    (
        "monitoring agent restarted",
        "the collector restarted and briefly reported gaps; the underlying service reported "
        "no errors across the gap",
        "collector restart: scrape gap 90s, backfilled",
    ),
)
"""Alerts that correspond to nothing.

Present so that "spend actions establishing an alert is benign" is a real cost
an operator can incur, and so that resolution counts cannot be inflated for
free by closing everything.
"""

ALL_REPAIRS: tuple[str, ...] = (
    "promote_read_replica",
    "rotate_certificate",
    "recycle_worker_pool",
    "resize_cache",
    "rebalance_partitions",
    "roll_back_deployment",
    "scale_out",
    "expand_volume",
    "restart_service",
    "apply_forward_fix",
)

SERVICE_BY_ID: dict[str, Service] = {service.service_id: service for service in SERVICES}
MODE_BY_ID: dict[str, FailureMode] = {
    mode.mode_id: mode for mode in FAILURE_MODES + SIDE_EFFECT_MODES
}


def subsystem_of_service(service_id: str) -> Subsystem:
    """Return the subsystem that owns a service."""
    service = SERVICE_BY_ID.get(service_id)
    if service is None:
        raise ValueError(f"unknown service: {service_id}")
    return service.subsystem
