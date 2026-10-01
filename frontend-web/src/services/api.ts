import axios from 'axios';

export const BACKEND_HOST = '13.53.197.95:8000';
export const API_BASE_URL = `http://${BACKEND_HOST}`;
export const WS_INCIDENTS_URL = `ws://${BACKEND_HOST}/ws/incidents`;

export interface Incident {
  id: number;
  title: string;
  description: string;
  status: 'investigating' | 'identified' | 'monitoring' | 'resolved' | string;
  severity: 'sev-1' | 'sev-2' | 'sev-3' | string;
  service_id: number;
  created_at: string;
}

export interface AuditLog {
  id: number;
  incident_id: number;
  action: string;
  details: string | null;
  timestamp: string;
}

export interface RagHistoricalMatch {
  incident_id: number;
  title: string;
  status: string;
  similarity_score: number;
  created_at: string;
}

export interface RagAnalysisResponse {
  incident_id: number;
  rag_pipeline: string;
  predicted_tag: string;
  confidence_pct: number;
  retrieved_runbook: {
    doc_id: string;
    tag: string;
    title: string;
    commands: string[];
    prevention: string;
  };
  retrieved_historical_incidents: RagHistoricalMatch[];
  generated_rca_summary: string;
}

export interface TelemetryMeta {
  traceId: string;
  cacheStatus: string;
  processTimeMs: string;
}

const API = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function fetchIncidentsWithTelemetry(): Promise<{
  incidents: Incident[];
  telemetry: TelemetryMeta;
}> {
  const res = await API.get<Incident[]>('/incidents/');
  return {
    incidents: res.data,
    telemetry: {
      traceId: res.headers['x-trace-id'] || 'N/A',
      cacheStatus: res.headers['x-cache'] || 'MISS',
      processTimeMs: res.headers['x-process-time-ms'] || '0',
    },
  };
}

export async function fetchIncidentAuditLogs(incidentId: number): Promise<AuditLog[]> {
  const res = await API.get<AuditLog[]>(`/incidents/${incidentId}/audit-logs`);
  return res.data;
}

export async function fetchIncidentRagAnalysis(incidentId: number): Promise<RagAnalysisResponse> {
  const res = await API.get<RagAnalysisResponse>(`/incidents/${incidentId}/rag-analysis`);
  return res.data;
}

export async function injectChaos(mode: 'error_500' | 'latency_spike', delayMs: number = 2200) {
  const res = await API.post(`/chaos/inject?mode=${mode}&delay_ms=${delayMs}`);
  return res.data;
}

export async function resetChaos() {
  const res = await API.post('/chaos/reset');
  return res.data;
}

export async function retrainAiModels() {
  const res = await API.post('/aiops/retrain');
  return res.data;
}

export default API;
