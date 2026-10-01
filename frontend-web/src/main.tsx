import React, { useEffect, useState, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import {
  WS_INCIDENTS_URL,
  fetchIncidentsWithTelemetry,
  fetchIncidentAuditLogs,
  fetchIncidentRagAnalysis,
  injectChaos,
  resetChaos,
  retrainAiModels,
  type Incident,
  type AuditLog,
  type RagAnalysisResponse,
  type TelemetryMeta,
} from './services/api';

function extractAiTag(text: string): string {
  const match = text.match(/\[([A-Z0-9_]+)\]/);
  return match ? match[1] : 'RUNTIME_ALERT';
}

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryMeta>({
    traceId: 'init',
    cacheStatus: 'MISS',
    processTimeMs: '0',
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [lastWsEvent, setLastWsEvent] = useState<string>('Waiting for real-time Redis Pub/Sub events...');
  const [statusBanner, setStatusBanner] = useState<string>('');

  // Inspector state for Audit Timeline & RAG Copilot
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [ragData, setRagData] = useState<RagAnalysisResponse | null>(null);
  const [inspectorLoading, setInspectorLoading] = useState<boolean>(false);

  const loadIncidents = useCallback(async () => {
    try {
      const data = await fetchIncidentsWithTelemetry();
      setIncidents(data.incidents);
      setTelemetry(data.telemetry);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching incidents:', err);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIncidents();
  }, [loadIncidents]);

  // Connect to FastAPI Real-Time WebSocket Stream (/ws/incidents)
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    const connectWs = () => {
      ws = new WebSocket(WS_INCIDENTS_URL);

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setLastWsEvent(`${parsed.event}: ${JSON.stringify(parsed.data)}`);
          if (parsed.event !== 'WS_CONNECTED') {
            loadIncidents();
          }
        } catch {
          setLastWsEvent(event.data);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        reconnectTimer = window.setTimeout(connectWs, 3000);
      };
    };

    connectWs();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, [loadIncidents]);

  const handleChaosInject = async (mode: 'error_500' | 'latency_spike') => {
    setStatusBanner(
      mode === 'error_500'
        ? '🔥 Injecting HTTP 500 Gateway Crash... Watch Celery detect & auto-heal in 10s!'
        : '🐢 Injecting 2200ms Latency Anomaly... Watch Predictive ML detector flag drift!'
    );
    await injectChaos(mode, 2200);
    setTimeout(loadIncidents, 2500);
    setTimeout(loadIncidents, 11500);
  };

  const handleChaosReset = async () => {
    await resetChaos();
    setStatusBanner('🟢 Chaos state reset to healthy. Active polling dispatched.');
    setTimeout(loadIncidents, 1500);
  };

  const handleRetrain = async () => {
    setStatusBanner('🧠 Retraining 256-D TF-IDF & Isolation Quantile ML models on EC2...');
    const res = await retrainAiModels();
    setStatusBanner(
      `✅ Model Artifact (${res.model_artifact}) Retrained! Baseline Median: ${res.metrics.baseline_median_ms}ms | Threshold: ${res.metrics.threshold_ms}ms`
    );
  };

  const handleInspectIncident = async (incidentId: number) => {
    setSelectedIncidentId(incidentId);
    setInspectorLoading(true);
    try {
      const [logs, rag] = await Promise.all([
        fetchIncidentAuditLogs(incidentId),
        fetchIncidentRagAnalysis(incidentId),
      ]);
      setAuditLogs(logs);
      setRagData(rag);
    } catch (err) {
      console.error('Error loading incident details:', err);
    } finally {
      setInspectorLoading(false);
    }
  };

  const activeCount = incidents.filter((i) => i.status !== 'resolved').length;

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', padding: '28px 36px', backgroundColor: '#0b0f19', color: '#f8fafc', minHeight: '100vh' }}>
      {/* Top Header & Observability Telemetry Bar */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', borderBottom: '1px solid #1e293b', paddingBottom: '20px', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
              OpsPilot AIOps Command Center
            </h1>
            <span style={{
              backgroundColor: wsConnected ? '#064e3b' : '#7f1d1d',
              color: wsConnected ? '#34d399' : '#fca5a5',
              padding: '4px 10px',
              borderRadius: '999px',
              fontSize: '0.75rem',
              fontWeight: 700,
              border: `1px solid ${wsConnected ? '#059669' : '#dc2626'}`
            }}>
              {wsConnected ? '● WS LIVE STREAM' : '○ WS RECONNECTING'}
            </span>
          </div>
          <p style={{ color: '#94a3b8', margin: '6px 0 0 0', fontSize: '0.9rem' }}>
            Autonomous Incident Detection, Vector NLP Triage, RAG Copilot & Self-Healing Engine
          </p>
        </div>

        {/* Distributed Tracing & Redis Cache Observability Pills */}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '8px 12px', borderRadius: '8px', fontSize: '0.8rem' }}>
            <span style={{ color: '#64748b' }}>X-Cache: </span>
            <strong style={{ color: telemetry.cacheStatus === 'HIT' ? '#34d399' : '#fbbf24' }}>
              {telemetry.cacheStatus}
            </strong>
          </div>
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '8px 12px', borderRadius: '8px', fontSize: '0.8rem' }}>
            <span style={{ color: '#64748b' }}>Latency: </span>
            <strong style={{ color: '#38bdf8' }}>{telemetry.processTimeMs} ms</strong>
          </div>
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', padding: '8px 12px', borderRadius: '8px', fontSize: '0.8rem', fontFamily: 'monospace' }}>
            <span style={{ color: '#64748b' }}>Trace: </span>
            <span style={{ color: '#cbd5e1' }}>{telemetry.traceId}</span>
          </div>
        </div>
      </header>

      {/* Chaos Engineering & MLOps Control Deck */}
      <section style={{ backgroundColor: '#111827', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px 20px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={() => handleChaosInject('error_500')}
            style={{ backgroundColor: '#dc2626', color: '#fff', border: 'none', padding: '10px 16px', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
          >
            💥 Inject 500 Gateway Crash (Auto-Heals in 10s)
          </button>
          <button
            onClick={() => handleChaosInject('latency_spike')}
            style={{ backgroundColor: '#d97706', color: '#fff', border: 'none', padding: '10px 16px', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
          >
            🐢 Inject 2200ms Latency Spike (Predictive ML)
          </button>
          <button
            onClick={handleChaosReset}
            style={{ backgroundColor: '#059669', color: '#fff', border: 'none', padding: '10px 16px', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
          >
            🟢 Reset Chaos State
          </button>
        </div>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={handleRetrain}
            style={{ backgroundColor: '#4f46e5', color: '#fff', border: 'none', padding: '10px 16px', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
          >
            🧠 Retrain ML Models (.npz)
          </button>
          <button
            onClick={loadIncidents}
            style={{ backgroundColor: '#1e293b', color: '#e2e8f0', border: '1px solid #334155', padding: '10px 16px', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem' }}
          >
            🔄 Refresh (Test Redis HIT)
          </button>
        </div>
      </section>

      {/* Live WebSocket Event Ticker & Status Notification */}
      <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px 16px', marginBottom: '24px', fontFamily: 'monospace', fontSize: '0.8rem', color: '#38bdf8', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <span>⚡ <strong>Live Pub/Sub Bus:</strong> {lastWsEvent}</span>
        {statusBanner && <span style={{ color: '#fbbf24' }}>{statusBanner}</span>}
      </div>

      {/* Main Split View: Incident Feed (Left) + RAG Copilot & Audit Inspector (Right) */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedIncidentId ? '1.15fr 0.85fr' : '1fr', gap: '24px', alignItems: 'start' }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem' }}>
              Incident Telemetry Feed ({incidents.length} total, {activeCount} active)
            </h2>
          </div>

          {loading ? (
            <p style={{ color: '#38bdf8' }}>Fetching live incidents from AWS EC2...</p>
          ) : incidents.length === 0 ? (
            <div style={{ backgroundColor: '#111827', padding: '24px', borderRadius: '10px', textAlign: 'center' }}>
              <p style={{ color: '#34d399', fontSize: '1.1rem', margin: 0 }}>✅ All systems operational. No incidents logged.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '14px' }}>
              {incidents.map((incident) => {
                const isResolved = incident.status === 'resolved';
                const aiTag = extractAiTag(incident.description || incident.title);
                const isSelected = selectedIncidentId === incident.id;

                return (
                  <div
                    key={incident.id}
                    style={{
                      backgroundColor: isSelected ? '#172033' : '#111827',
                      padding: '18px 20px',
                      borderRadius: '10px',
                      border: isSelected ? '1px solid #38bdf8' : '1px solid #1e293b',
                      borderLeft: `5px solid ${isResolved ? '#10b981' : incident.severity === 'sev-1' ? '#ef4444' : '#f59e0b'}`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '0.8rem' }}>
                          #{incident.id}
                        </span>
                        <span style={{
                          backgroundColor: incident.severity === 'sev-1' ? '#7f1d1d' : '#78350f',
                          color: incident.severity === 'sev-1' ? '#fca5a5' : '#fde68a',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          textTransform: 'uppercase'
                        }}>
                          {incident.severity}
                        </span>
                        <span style={{
                          backgroundColor: '#1e1b4b',
                          color: '#a5b4fc',
                          border: '1px solid #3730a3',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '0.72rem',
                          fontFamily: 'monospace',
                          fontWeight: 600
                        }}>
                          🧠 {aiTag}
                        </span>
                      </div>

                      <span style={{
                        backgroundColor: isResolved ? '#064e3b' : '#451a03',
                        color: isResolved ? '#34d399' : '#fbbf24',
                        padding: '3px 10px',
                        borderRadius: '999px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        textTransform: 'uppercase'
                      }}>
                        {isResolved ? '✓ RESOLVED (AI HEALED)' : `● ${incident.status}`}
                      </span>
                    </div>

                    <h3 style={{ margin: '0 0 8px 0', fontSize: '1.05rem', color: '#f1f5f9' }}>
                      {incident.title}
                    </h3>
                    <p style={{ margin: '0 0 14px 0', color: '#94a3b8', fontSize: '0.88rem', lineHeight: 1.5 }}>
                      {incident.description}
                    </p>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                      <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                        Logged: {new Date(incident.created_at).toLocaleString()}
                      </span>
                      <button
                        onClick={() => handleInspectIncident(incident.id)}
                        style={{
                          backgroundColor: '#0284c7',
                          color: '#fff',
                          border: 'none',
                          padding: '7px 14px',
                          borderRadius: '6px',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          cursor: 'pointer'
                        }}
                      >
                        🤖 Inspect RAG Copilot & Audit Trail →
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: RAG Copilot & Millisecond Audit Trail Drawer */}
        {selectedIncidentId && (
          <aside style={{ backgroundColor: '#111827', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', position: 'sticky', top: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', paddingBottom: '12px', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#38bdf8' }}>
                🤖 Incident #{selectedIncidentId} RAG Copilot & Audit
              </h3>
              <button
                onClick={() => setSelectedIncidentId(null)}
                style={{ background: 'transparent', color: '#94a3b8', border: '1px solid #334155', borderRadius: '6px', padding: '4px 10px', cursor: 'pointer' }}
              >
                ✕ Close
              </button>
            </div>

            {inspectorLoading ? (
              <p style={{ color: '#38bdf8' }}>Running 256-D Vector Retrieval & loading Audit Trail...</p>
            ) : (
              <>
                {ragData && (
                  <div style={{ marginBottom: '20px' }}>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
                      <span style={{ backgroundColor: '#1e1b4b', color: '#c7d2fe', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 700 }}>
                        Tag: {ragData.predicted_tag}
                      </span>
                      <span style={{ backgroundColor: '#064e3b', color: '#6ee7b7', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 700 }}>
                        Cosine Confidence: {ragData.confidence_pct}%
                      </span>
                      <span style={{ backgroundColor: '#1f2937', color: '#cbd5e1', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                        {ragData.retrieved_runbook.doc_id}
                      </span>
                    </div>

                    <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', padding: '12px', borderRadius: '8px', fontSize: '0.85rem', color: '#e2e8f0', lineHeight: 1.5, marginBottom: '14px' }}>
                      {ragData.generated_rca_summary}
                    </div>

                    <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: '#94a3b8', textTransform: 'uppercase' }}>
                      📟 Retrieved CLI Remediation Runbook ({ragData.retrieved_runbook.title})
                    </h4>
                    <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px 12px', fontFamily: 'monospace', fontSize: '0.78rem', color: '#34d399', marginBottom: '14px', overflowX: 'auto' }}>
                      {ragData.retrieved_runbook.commands.map((cmd, idx) => (
                        <div key={idx} style={{ marginBottom: '6px' }}>$ {cmd}</div>
                      ))}
                    </div>

                    <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: '#94a3b8', textTransform: 'uppercase' }}>
                      🔍 Top-K Vector Similar Past Incidents (PostgreSQL)
                    </h4>
                    <div style={{ display: 'grid', gap: '6px', marginBottom: '18px' }}>
                      {ragData.retrieved_historical_incidents.map((match) => (
                        <div key={match.incident_id} style={{ backgroundColor: '#0f172a', padding: '8px 10px', borderRadius: '6px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between' }}>
                          <span>#{match.incident_id}: {match.title.slice(0, 42)}...</span>
                          <strong style={{ color: '#38bdf8' }}>{match.similarity_score}% match</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <h4 style={{ margin: '0 0 10px 0', fontSize: '0.85rem', color: '#94a3b8', textTransform: 'uppercase' }}>
                  ⏱️ Millisecond Audit Log Timeline ({auditLogs.length} events)
                </h4>
                <div style={{ display: 'grid', gap: '8px', maxHeight: '260px', overflowY: 'auto' }}>
                  {auditLogs.map((log) => (
                    <div key={log.id} style={{ backgroundColor: '#0f172a', borderLeft: '3px solid #38bdf8', padding: '8px 12px', borderRadius: '6px', fontSize: '0.8rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8', fontWeight: 700, marginBottom: '4px' }}>
                        <span>{log.action}</span>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#64748b' }}>
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div style={{ color: '#cbd5e1', lineHeight: 1.4 }}>{log.details}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
