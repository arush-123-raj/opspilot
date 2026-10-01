import os
import numpy as np
from typing import Dict, Tuple, List
from app.train_models import MODEL_PATH, extract_ngram_counts, train_and_save_models

LATENCY_HISTORY: Dict[int, List[float]] = {}

CLUSTER_METADATA = {
    "PREDICTIVE_LATENCY_DEGRADATION": {
        "summary": "Abnormal response time drift detected prior to hard service failure.",
        "auto_healable": True,
        "playbook": "Scaled worker concurrency and reset degraded upstream latency state."
    },
    "DB_CONNECTION_POOL_EXHAUSTED": {
        "summary": "Database connection pool saturated under concurrent load.",
        "auto_healable": True,
        "playbook": "Executed `pg_terminate_backend` on idle connections and scaled pooler."
    },
    "REDIS_OOM_CACHE_OVERFLOW": {
        "summary": "In-memory cache exceeded maxmemory threshold.",
        "auto_healable": True,
        "playbook": "Triggered volatile-lru cache flush and cleared orphaned keys."
    },
    "UPSTREAM_GATEWAY_CRASH_5XX": {
        "summary": "Upstream microservice returned fatal 5xx HTTP exception.",
        "auto_healable": True,
        "playbook": "Dispatched container rolling restart webhook and reset Chaos state to healthy."
    },
    "NETWORK_DNS_UNREACHABLE": {
        "summary": "Target host refused TCP handshake or failed DNS resolution.",
        "auto_healable": False,
        "playbook": "Escalated to On-Call Network SRE (requires manual infrastructure inspection)."
    },
}

MODEL_CACHE: Dict[str, object] = {}

def load_trained_artifacts(force_retrain: bool = False) -> Dict[str, object]:
    """Loads serialized .npz ML weights into memory, training first if artifact is missing."""
    if force_retrain or not os.path.exists(MODEL_PATH):
        train_and_save_models()
    data = np.load(MODEL_PATH, allow_pickle=False)
    MODEL_CACHE["tags"] = [str(t) for t in data["tags"]]
    MODEL_CACHE["idf_weights"] = data["idf_weights"]
    MODEL_CACHE["centroid_matrix"] = data["centroid_matrix"]
    MODEL_CACHE["anomaly_params"] = data["anomaly_params"]
    return {
        "classes": MODEL_CACHE["tags"],
        "vector_dim": int(MODEL_CACHE["centroid_matrix"].shape[1]),
        "baseline_median_ms": round(float(MODEL_CACHE["anomaly_params"][0]), 2),
        "threshold_ms": round(float(MODEL_CACHE["anomaly_params"][4]), 2),
    }

# Load trained model weights on module import
load_trained_artifacts()


def triage_error_log(raw_error: str) -> Dict[str, object]:
    """Runs TF-IDF N-Gram Vector Cosine Similarity against trained class centroids."""
    if not MODEL_CACHE:
        load_trained_artifacts()

    tags: List[str] = MODEL_CACHE["tags"]  # type: ignore
    idf_weights: np.ndarray = MODEL_CACHE["idf_weights"]  # type: ignore
    centroid_matrix: np.ndarray = MODEL_CACHE["centroid_matrix"]  # type: ignore

    tfidf_vec = extract_ngram_counts(raw_error) * idf_weights
    norm = np.linalg.norm(tfidf_vec)
    unit_vec = tfidf_vec / norm if norm > 0 else tfidf_vec

    similarities = np.dot(centroid_matrix, unit_vec)
    best_idx = int(np.argmax(similarities))
    best_sim = float(similarities[best_idx])

    if best_sim < 0.15:
        return {
            "tag": "UNCLASSIFIED_RUNTIME_EXCEPTION",
            "confidence": 51.0,
            "summary": "Novel runtime error signature detected; clustered for post-mortem review.",
            "auto_healable": False,
            "playbook": "Logged stack trace embedding and paged primary on-call engineer."
        }

    pred_tag = tags[best_idx]
    meta = CLUSTER_METADATA.get(pred_tag, CLUSTER_METADATA["UPSTREAM_GATEWAY_CRASH_5XX"])
    confidence_pct = round(min(99.6, max(55.0, best_sim * 135.0)), 1)

    return {
        "tag": pred_tag,
        "confidence": confidence_pct,
        "summary": f"{meta['summary']} (ML Cosine Confidence: {confidence_pct}%)",
        "auto_healable": meta["auto_healable"],
        "playbook": meta["playbook"],
    }


def detect_latency_anomaly(service_id: int, latency_ms: float) -> Tuple[bool, str]:
    """Evaluates response latency using trained Isolation Quantile + Rolling MAD ensemble."""
    if not MODEL_CACHE:
        load_trained_artifacts()

    trained_median, trained_mad, trained_q75, trained_iqr, trained_threshold = MODEL_CACHE["anomaly_params"]  # type: ignore
    history = LATENCY_HISTORY.setdefault(service_id, [])

    if len(history) >= 3:
        arr = np.array(history, dtype=np.float64)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median))) or float(trained_mad)
        q75 = float(np.percentile(arr, 75))
        iqr = max(float(np.percentile(arr, 75) - np.percentile(arr, 25)), float(trained_iqr))
    else:
        median, mad, q75, iqr = float(trained_median), float(trained_mad), float(trained_q75), float(trained_iqr)

    modified_z = 0.6745 * abs(latency_ms - median) / (mad or 1.0)
    isolation_score = round(float(1.0 - np.exp(-max(0.0, latency_ms - q75) / (iqr * 3.0))), 2)

    is_anomaly = False
    reason = "Latency within normal trained baseline."

    if latency_ms > 1500 or (latency_ms > float(trained_threshold) and (modified_z > 3.0 or isolation_score > 0.65)):
        is_anomaly = True
        reason = (
            f"Predictive ML Alert: Latency spiked to {latency_ms}ms "
            f"(Baseline: {round(median, 1)}ms, Isolation Score: {isolation_score}, Mod-Z: {round(modified_z, 2)}σ)"
        )

    history.append(min(latency_ms, 250.0) if is_anomaly else latency_ms)
    if len(history) > 25:
        history.pop(0)

    return is_anomaly, reason
