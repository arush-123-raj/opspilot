import os
import re
import zlib
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), "aiops_model_weights.npz")
VECTOR_DIM = 256

# Labeled training corpus of production infrastructure failure logs
TRAINING_CORPUS = [
    ("PREDICTIVE_LATENCY_DEGRADATION", "predictive ml alert latency spiked z-score degraded response time drift slow upstream timeout warning high p99 latency"),
    ("PREDICTIVE_LATENCY_DEGRADATION", "upstream service responding slowly 2200ms latency anomaly detected before crash"),
    ("DB_CONNECTION_POOL_EXHAUSTED", "fatal database connection pool exhausted too many clients remaining connection slots reserved superuser timeout 503 504"),
    ("DB_CONNECTION_POOL_EXHAUSTED", "sqlalchemy asyncpg QueuePool limit of size 5 overflow 10 reached connection timed out"),
    ("REDIS_OOM_CACHE_OVERFLOW", "redis oom out of memory command not allowed used memory greater than maxmemory eviction cache overflow"),
    ("REDIS_OOM_CACHE_OVERFLOW", "redis connection error maxmemory policy volatile-lru triggered memory fragmentation spike"),
    ("UPSTREAM_GATEWAY_CRASH_5XX", "http 500 502 internal server error bad gateway chaos simulated fatal upstream microservice crash exception"),
    ("UPSTREAM_GATEWAY_CRASH_5XX", "500 server error from http api 8000 chaos target upstream gateway failed"),
    ("NETWORK_DNS_UNREACHABLE", "network dns resolution failed name or service not known connection refused unreachable host tcp handshake"),
    ("NETWORK_DNS_UNREACHABLE", "socket gaierror errno -2 name or service not known dial tcp connection refused"),
]

def extract_ngram_counts(text: str, dim: int = VECTOR_DIM) -> np.ndarray:
    cleaned = re.sub(r"[^a-z0-9_ ]+", " ", text.lower())
    counts = np.zeros(dim, dtype=np.float64)
    for token in cleaned.split():
        counts[zlib.crc32(token.encode("utf-8")) % dim] += 2.0
    padded = f" {cleaned} "
    for i in range(len(padded) - 2):
        counts[zlib.crc32(padded[i : i + 3].encode("utf-8")) % dim] += 1.0
    return counts

def train_and_save_models():
    print("🚀 [ML Trainer] Starting OpsPilot AIOps Model Training Pipeline...")

    # 1. Train Unsupervised Latency Anomaly Detector on 1,000 synthetic baseline telemetry samples
    rng = np.random.default_rng(42)
    normal_latencies = rng.normal(loc=18.0, scale=6.5, size=950).clip(min=1.5)
    spike_outliers = rng.uniform(low=450.0, high=3500.0, size=50)
    telemetry_dataset = np.concatenate([normal_latencies, spike_outliers])

    # Fit robust Isolation Quantiles & Median Absolute Deviation (MAD) parameters
    trained_median = float(np.median(normal_latencies))
    trained_mad = float(np.median(np.abs(normal_latencies - trained_median))) or 1.0
    q25, q75, q99 = np.percentile(telemetry_dataset, [25, 75, 95])
    trained_iqr = max(float(q75 - q25), 1.0)
    trained_threshold_ms = max(200.0, float(q99))

    print(f"✅ [ML Anomaly Model Fit] Samples: {len(telemetry_dataset)} | Baseline Median: {trained_median:.2f}ms | IQR: {trained_iqr:.2f}ms | Auto-Threshold: {trained_threshold_ms:.2f}ms")

    # 2. Train NLP TF-IDF Vectorizer & Class Centroid Embeddings
    tags = sorted(list({label for label, _ in TRAINING_CORPUS}))
    doc_matrix = np.array([extract_ngram_counts(text) for _, text in TRAINING_CORPUS])

    # Compute Inverse Document Frequency (IDF) weights across corpus
    doc_freq = np.sum(doc_matrix > 0, axis=0)
    idf_weights = np.log((len(TRAINING_CORPUS) + 1.0) / (doc_freq + 1.0)) + 1.0

    # Compute normalized TF-IDF centroid vectors for each root-cause class
    centroids = []
    for tag in tags:
        class_vecs = [
            extract_ngram_counts(text) * idf_weights
            for label, text in TRAINING_CORPUS if label == tag
        ]
        centroid = np.mean(class_vecs, axis=0)
        norm = np.linalg.norm(centroid)
        centroids.append(centroid / norm if norm > 0 else centroid)

    centroid_matrix = np.vstack(centroids)

    # Evaluate training accuracy on corpus
    correct = 0
    for label, text in TRAINING_CORPUS:
        vec = extract_ngram_counts(text) * idf_weights
        vec = vec / (np.linalg.norm(vec) or 1.0)
        sims = np.dot(centroid_matrix, vec)
        pred_tag = tags[int(np.argmax(sims))]
        if pred_tag == label:
            correct += 1
    accuracy = (correct / len(TRAINING_CORPUS)) * 100.0
    print(f"✅ [NLP Vector Model Fit] Classes: {len(tags)} | Vector Dim: {VECTOR_DIM} | Training Accuracy: {accuracy:.1f}%")

    # 3. Serialize trained weights to disk (.npz)
    np.savez(
        MODEL_PATH,
        tags=np.array(tags),
        idf_weights=idf_weights,
        centroid_matrix=centroid_matrix,
        anomaly_params=np.array([trained_median, trained_mad, float(q75), trained_iqr, trained_threshold_ms], dtype=np.float64),
    )
    print(f"💾 [Artifact Saved] Trained model weights serialized to: {MODEL_PATH}")

if __name__ == "__main__":
    train_and_save_models()
