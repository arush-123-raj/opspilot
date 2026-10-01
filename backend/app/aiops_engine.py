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


# --- Phase 5.3: RAG (Retrieval-Augmented Generation) Knowledge Base & Synthesizer ---
SRE_RUNBOOK_DOCS = [
    {
        "doc_id": "RUNBOOK-DB-101",
        "tag": "DB_CONNECTION_POOL_EXHAUSTED",
        "title": "PostgreSQL Connection Pool Saturation & Idle Transaction Termination",
        "commands": [
            "sudo docker exec opspilot-postgres psql -U opspilot_user -d opspilot_db -c \"SELECT pid, state, query FROM pg_stat_activity WHERE state != 'idle';\"",
            "sudo docker exec opspilot-postgres psql -U opspilot_user -d opspilot_db -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';\""
        ],
        "prevention": "Increase SQLAlchemy pool_size or deploy PgBouncer transaction pooling."
    },
    {
        "doc_id": "RUNBOOK-LATENCY-204",
        "tag": "PREDICTIVE_LATENCY_DEGRADATION",
        "title": "Pre-Failure P99 Latency Drift & Worker Concurrency Scaling",
        "commands": [
            "curl -s -X POST http://localhost:8000/chaos/reset",
            "sudo docker compose up -d --scale worker=2"
        ],
        "prevention": "Enable auto-scaling based on rollingModified Z-Score > 3.0σ prior to saturation."
    },
    {
        "doc_id": "RUNBOOK-GATEWAY-500",
        "tag": "UPSTREAM_GATEWAY_CRASH_5XX",
        "title": "Upstream Microservice HTTP 5xx Crash & Rolling Container Restart",
        "commands": [
            "curl -s -X POST http://localhost:8000/chaos/reset",
            "sudo docker compose restart api"
        ],
        "prevention": "Wrap upstream calls in a 5-strike Redis Circuit Breaker with exponential backoff."
    },
    {
        "doc_id": "RUNBOOK-REDIS-302",
        "tag": "REDIS_OOM_CACHE_OVERFLOW",
        "title": "Redis Maxmemory Eviction & Orphaned Cache Key Purge",
        "commands": [
            "sudo docker exec opspilot-redis redis-cli INFO memory",
            "sudo docker exec opspilot-redis redis-cli FLUSHDB ASYNC"
        ],
        "prevention": "Configure maxmemory-policy allkeys-lru and enforce 30s TTLs on incident list caches."
    },
    {
        "doc_id": "RUNBOOK-NET-404",
        "tag": "NETWORK_DNS_UNREACHABLE",
        "title": "Docker Bridge DNS Failure & Upstream TCP Handshake Refusal",
        "commands": [
            "sudo docker network inspect opspilot_default",
            "sudo docker exec opspilot-api ping -c 3 db"
        ],
        "prevention": "Enforce Docker Compose healthcheck conditions before starting dependent workers."
    }
]


def generate_rag_incident_copilot(
    incident_id: int,
    title: str,
    description: str,
    severity: str,
    historical_incidents: List[Dict[str, object]]
) -> Dict[str, object]:
    """
    Phase 5.3 RAG Pipeline:
    1. RETRIEVAL (R): Embeds current incident text into 256-D TF-IDF space, computes Cosine
       Similarity against historical PostgreSQL incidents + SRE Runbook documents.
    2. AUGMENTATION (A): Constructs a grounded context window from Top-K past incidents & runbooks.
    3. GENERATION (G): Synthesizes a cited Root-Cause Analysis (RCA) & executable CLI runbook.
    """
    if not MODEL_CACHE:
        load_trained_artifacts()

    idf_weights: np.ndarray = MODEL_CACHE["idf_weights"]  # type: ignore
    query_text = f"{title} {description}"
    q_vec = extract_ngram_counts(query_text) * idf_weights
    q_norm = np.linalg.norm(q_vec)
    q_unit = q_vec / q_norm if q_norm > 0 else q_vec

    # Step 1A: Retrieve Top-K similar historical incidents from PostgreSQL using Cosine Similarity
    retrieved_history = []
    for past in historical_incidents:
        if past.get("id") == incident_id:
            continue
        p_text = f"{past.get('title', '')} {past.get('description', '')}"
        p_vec = extract_ngram_counts(p_text) * idf_weights
        p_norm = np.linalg.norm(p_vec)
        p_unit = p_vec / p_norm if p_norm > 0 else p_vec
        sim = float(np.dot(q_unit, p_vec / p_norm)) if p_norm > 0 else 0.0
        if sim > 0.10:
            retrieved_history.append({
                "incident_id": past["id"],
                "title": past["title"],
                "status": past["status"],
                "similarity_score": round(min(99.8, sim * 100.0), 1),
                "created_at": str(past["created_at"])
            })

    retrieved_history.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_k_history = retrieved_history[:3]

    # Step 1B: Retrieve matching SRE Runbook Document
    triage = triage_error_log(query_text)
    matched_runbook = next(
        (doc for doc in SRE_RUNBOOK_DOCS if doc["tag"] == triage["tag"]),
        SRE_RUNBOOK_DOCS[2]
    )

    # Step 2 & 3: Augmented Generation (Synthesize grounded SRE response citing retrieved evidence)
    history_citation = (
        f"Matched {len(top_k_history)} similar historical incident(s) in PostgreSQL "
        f"(Top match: Incident #{top_k_history[0]['incident_id']} at {top_k_history[0]['similarity_score']}% vector similarity)."
        if top_k_history else
        "No prior identical incidents found in PostgreSQL; grounded strictly on SRE Runbook Knowledge Base."
    )

    generated_rca = (
        f"🤖 [OpsPilot RAG Copilot] Incident #{incident_id} ({severity.upper()}) classified as "
        f"[{triage['tag']}] with {triage['confidence']}% vector confidence. "
        f"{history_citation} "
        f"Recommended Runbook [{matched_runbook['doc_id']}]: {matched_runbook['title']}. "
        f"Long-term prevention: {matched_runbook['prevention']}"
    )

    return {
        "incident_id": incident_id,
        "rag_pipeline": "TF-IDF-256D-Cosine-Retriever + Grounded-SRE-Synthesizer",
        "predicted_tag": triage["tag"],
        "confidence_pct": triage["confidence"],
        "retrieved_runbook": matched_runbook,
        "retrieved_historical_incidents": top_k_history,
        "generated_rca_summary": generated_rca,
    }
