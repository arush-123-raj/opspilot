import math
from typing import Dict, Tuple, List

LATENCY_HISTORY: Dict[int, List[float]] = {}

SIGNATURE_CLUSTERS = [
    {
        "tag": "PREDICTIVE_LATENCY_DEGRADATION",
        "keywords": ["predictive ml alert", "latency spiked", "z-score", "degraded"],
        "summary": "Abnormal response time drift detected prior to hard service failure.",
        "auto_healable": True,
        "playbook": "Scaled worker concurrency and reset degraded upstream latency state."
    },
    {
        "tag": "DB_CONNECTION_POOL_EXHAUSTED",
        "keywords": ["connection", "pool", "too many clients", "timeout", "remaining connection slots", "503", "504"],
        "summary": "Database connection pool saturated under concurrent load.",
        "auto_healable": True,
        "playbook": "Executed `pg_terminate_backend` on idle connections and scaled pooler."
    },
    {
        "tag": "REDIS_OOM_CACHE_OVERFLOW",
        "keywords": ["oom", "memory", "redis", "maxmemory", "eviction", "cache"],
        "summary": "In-memory cache exceeded maxmemory threshold.",
        "auto_healable": True,
        "playbook": "Triggered volatile-lru cache flush and cleared orphaned keys."
    },
    {
        "tag": "UPSTREAM_GATEWAY_CRASH_5XX",
        "keywords": ["500", "502", "internal server error", "bad gateway", "chaos", "simulated"],
        "summary": "Upstream microservice returned fatal 5xx HTTP exception.",
        "auto_healable": True,
        "playbook": "Dispatched container rolling restart webhook and reset Chaos state to healthy."
    },
    {
        "tag": "NETWORK_DNS_UNREACHABLE",
        "keywords": ["dns", "name or service not known", "connection refused", "unreachable"],
        "summary": "Target host refused TCP handshake or failed DNS resolution.",
        "auto_healable": False,
        "playbook": "Escalated to On-Call Network SRE (requires manual infrastructure inspection)."
    },
]

def triage_error_log(raw_error: str) -> Dict[str, object]:
    lower_err = raw_error.lower()
    best_cluster = None
    max_hits = 0

    for cluster in SIGNATURE_CLUSTERS:
        hits = sum(1 for kw in cluster["keywords"] if kw in lower_err)
        if hits > max_hits:
            max_hits = hits
            best_cluster = cluster

    if not best_cluster:
        return {
            "tag": "UNCLASSIFIED_RUNTIME_EXCEPTION",
            "summary": "Novel runtime error signature detected; clustered for post-mortem review.",
            "auto_healable": False,
            "playbook": "Logged stack trace embedding and paged primary on-call engineer."
        }
    return best_cluster

def detect_latency_anomaly(service_id: int, latency_ms: float) -> Tuple[bool, str]:
    history = LATENCY_HISTORY.setdefault(service_id, [])
    is_anomaly = False
    reason = "Latency within normal baseline."

    # Only flag anomalies when latency exceeds 200ms (ignores 5-15ms local jitter)
    if len(history) >= 3:
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std_dev = math.sqrt(variance) or 1.0
        z_score = (latency_ms - mean) / std_dev

        if latency_ms > 1500 or (latency_ms > 200 and z_score > 2.5 and latency_ms > mean * 2):
            is_anomaly = True
            reason = (
                f"Predictive ML Alert: Latency spiked to {latency_ms}ms "
                f"(Baseline mean: {round(mean, 1)}ms, Z-Score: {round(z_score, 2)}σ)"
            )
    elif latency_ms > 1500:
        is_anomaly = True
        reason = f"Predictive ML Alert: Severe initial latency spike ({latency_ms}ms > 1500ms threshold)"

    history.append(latency_ms)
    if len(history) > 20:
        history.pop(0)

    return is_anomaly, reason
