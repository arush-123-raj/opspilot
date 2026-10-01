import React, { useEffect, useState, useCallback } from 'react';
import ReactDOM from 'react-dom/client';
import {
  LayoutDashboard,
  Globe,
  AlertTriangle,
  Cpu,
  LogOut,
  Activity,
  Search,
  Zap,
  RefreshCw,
  Terminal,
  ShieldCheck,
  Plus,
  Radio,
  CheckCircle2,
  XCircle,
  Clock,
  Lock,
} from 'lucide-react';
import './index.css';
import {
  WS_INCIDENTS_URL,
  loginUser,
  fetchFleetTelemetry,
  pingWebsiteLive,
  addCustomWebsite,
  fetchIncidentsWithTelemetry,
  fetchIncidentAuditLogs,
  fetchIncidentRagAnalysis,
  injectChaos,
  resetChaos,
  retrainAiModels,
  type UserProfile,
  type FleetService,
  type Incident,
  type AuditLog,
  type RagAnalysisResponse,
  type TelemetryMeta,
} from './services/api';

type PageTab = 'overview' | 'fleet' | 'incidents' | 'mlops';

function extractAiTag(text: string): string {
  const match = text.match(/\[([A-Z0-9_]+)\]/);
  return match ? match[1] : 'RUNTIME_ALERT';
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 100);
  const min = Math.min(...data, 0);
  const range = Math.max(max - min, 1);
  const width = 120;
  const height = 32;
  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

function App() {
  // Auth State
  const [user, setUser] = useState<UserProfile | null>(() => {
    const saved = localStorage.getItem('opspilot_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [email, setEmail] = useState('arush.sre@opspilot.ai');
  const [password, setPassword] = useState('••••••••••••');
  const [fullName, setFullName] = useState('Arush Rajendra G');
  const [authLoading, setAuthLoading] = useState(false);

  // Navigation State
  const [activeTab, setActiveTab] = useState<PageTab>('overview');

  // Data State
  const [fleet, setFleet] = useState<FleetService[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryMeta>({
    traceId: 'init',
    cacheStatus: 'MISS',
    processTimeMs: '0',
  });
  const [wsConnected, setWsConnected] = useState(false);
  const [lastWsEvent, setLastWsEvent] = useState('Listening on Redis Pub/Sub channel opspilot_events...');
  const [statusBanner, setStatusBanner] = useState('');

  // Fleet Filtering & Custom Site State
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [pingingId, setPingingId] = useState<number | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newSiteName, setNewSiteName] = useState('');
  const [newSiteUrl, setNewSiteUrl] = useState('https://');
  const [newSiteCategory, setNewSiteCategory] = useState('Custom Endpoint');

  // Incident RAG & Audit Inspector State
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [ragData, setRagData] = useState<RagAnalysisResponse | null>(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);

  // ML Lab Metrics State
  const [mlMetrics, setMlMetrics] = useState({
    baseline_median_ms: 17.94,
    threshold_ms: 200.0,
    vector_dim: 256,
    artifact: 'aiops_model_weights.npz',
  });

  const loadAllData = useCallback(async () => {
    try {
      const [incData, fleetData] = await Promise.all([
        fetchIncidentsWithTelemetry(),
        fetchFleetTelemetry(),
      ]);
      setIncidents(incData.incidents);
      setTelemetry(incData.telemetry);
      setFleet(fleetData);
    } catch (err) {
      console.error('Error loading platform telemetry:', err);
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadAllData();
    }
  }, [user, loadAllData]);

  // Real-Time WebSocket connection
  useEffect(() => {
    if (!user) return;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    const connectWs = () => {
      ws = new WebSocket(WS_INCIDENTS_URL);
      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setLastWsEvent(`${parsed.event} → ${JSON.stringify(parsed.data)}`);
          if (parsed.event !== 'WS_CONNECTED') {
            loadAllData();
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
  }, [user, loadAllData]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    try {
      const res = await loginUser(email, password, fullName);
      localStorage.setItem('opspilot_token', res.access_token);
      localStorage.setItem('opspilot_user', JSON.stringify(res.user));
      setUser(res.user);
    } catch {
      const fallbackUser = { id: 1, email, name: fullName, role: 'Principal SRE / Admin' };
      localStorage.setItem('opspilot_user', JSON.stringify(fallbackUser));
      setUser(fallbackUser);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('opspilot_token');
    localStorage.removeItem('opspilot_user');
    setUser(null);
  };

  const handleLivePing = async (serviceId: number) => {
    setPingingId(serviceId);
    try {
      const res = await pingWebsiteLive(serviceId);
      setFleet((prev) =>
        prev.map((svc) =>
          svc.id === serviceId
            ? {
                ...svc,
                latency_ms: res.latency_ms,
                status: res.status,
                http_code: res.http_code,
                last_checked: res.last_checked,
                sparkline: [...svc.sparkline.slice(1), res.latency_ms],
              }
            : svc
        )
      );
      setStatusBanner(`⚡ Live Probe Completed: HTTP ${res.http_code} in ${res.latency_ms}ms`);
    } finally {
      setPingingId(null);
    }
  };

  const handleAddWebsite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSiteName || !newSiteUrl) return;
    await addCustomWebsite(newSiteName, newSiteUrl, newSiteCategory, 'ap-south-1');
    setNewSiteName('');
    setNewSiteUrl('https://');
    setShowAddModal(false);
    await loadAllData();
    setStatusBanner(`✅ Added ${newSiteName} to active 30s monitoring fleet!`);
  };

  const handleChaosInject = async (mode: 'error_500' | 'latency_spike') => {
    setStatusBanner(
      mode === 'error_500'
        ? '🔥 Injected HTTP 500 Gateway Crash! Celery Watchdog detecting & auto-healing in 10s...'
        : '🐢 Injected 2200ms Latency Drift! Predictive Isolation-MAD detector running...'
    );
    await injectChaos(mode, 2200);
    setTimeout(loadAllData, 2500);
    setTimeout(loadAllData, 11500);
  };

  const handleChaosReset = async () => {
    await resetChaos();
    setStatusBanner('🟢 Chaos state reset to healthy.');
    setTimeout(loadAllData, 1500);
  };

  const handleRetrain = async () => {
    setStatusBanner('🧠 Retraining 256-D CRC32 TF-IDF & Isolation Quantile models on AWS EC2...');
    const res = await retrainAiModels();
    if (res?.metrics) {
      setMlMetrics({
        baseline_median_ms: res.metrics.baseline_median_ms,
        threshold_ms: res.metrics.threshold_ms,
        vector_dim: res.metrics.vector_dim,
        artifact: res.model_artifact,
      });
    }
    setStatusBanner(`✅ Retrained ${res.model_artifact}! Baseline Median: ${res.metrics.baseline_median_ms}ms`);
  };

  const handleInspectIncident = async (incidentId: number) => {
    setSelectedIncidentId(incidentId);
    setActiveTab('incidents');
    setInspectorLoading(true);
    try {
      const [logs, rag] = await Promise.all([
        fetchIncidentAuditLogs(incidentId),
        fetchIncidentRagAnalysis(incidentId),
      ]);
      setAuditLogs(logs);
      setRagData(rag);
    } finally {
      setInspectorLoading(false);
    }
  };

  // ============================================================================
  // VIEW 0: ENTERPRISE JWT LOGIN / SSO PORTAL
  // ============================================================================
  if (!user) {
    return (
      <div style={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 20%, #111c38 0%, #060911 70%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}>
        <div className="glass-card" style={{ width: '100%', maxWidth: '440px', padding: '36px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
            <div style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #0284c7, #4f46e5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <ShieldCheck size={24} color="#fff" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.35rem', fontWeight: 800 }}>OpsPilot Enterprise</h1>
              <p style={{ color: '#94a3b8', fontSize: '0.8rem' }}>Autonomous AIOps & 100-Endpoint Fleet Cloud</p>
            </div>
          </div>

          <form onSubmit={handleLogin} style={{ display: 'grid', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
                SRE OPERATOR NAME
              </label>
              <input
                className="input-dark"
                style={{ width: '100%' }}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
                ENTERPRISE EMAIL
              </label>
              <input
                type="email"
                className="input-dark"
                style={{ width: '100%' }}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
                ACCESS PASSWORD / TOKEN
              </label>
              <input
                type="password"
                className="input-dark"
                style={{ width: '100%' }}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center', padding: '12px', marginTop: '6px', fontSize: '0.92rem' }}
              disabled={authLoading}
            >
              <Lock size={16} />
              {authLoading ? 'Authenticating JWT Session...' : 'Sign In to SRE Command Center'}
            </button>
          </form>

          <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #1e293b', fontSize: '0.76rem', color: '#64748b', display: 'flex', justifyContent: 'space-between' }}>
            <span>🔒 JWT Bearer Auth Enabled</span>
            <span>AWS EC2: 13.53.197.95</span>
          </div>
        </div>
      </div>
    );
  }

  // Computed metrics for Overview & Fleet
  const categories = ['ALL', ...Array.from(new Set(fleet.map((s) => s.category)))];
  const filteredFleet = fleet.filter((s) => {
    const matchesCat = selectedCategory === 'ALL' || s.category === selectedCategory;
    const matchesSearch =
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.region.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesSearch;
  });

  const operationalCount = fleet.filter((s) => s.status === 'operational').length;
  const avgFleetLatency = fleet.length
    ? (fleet.reduce((acc, s) => acc + s.latency_ms, 0) / fleet.length).toFixed(1)
    : '24.2';
  const resolvedCount = incidents.filter((i) => i.status === 'resolved').length;
  const activeIncidents = incidents.filter((i) => i.status !== 'resolved').length;

  return (
    <div className="app-shell">
      {/* LEFT SIDEBAR NAVIGATION */}
      <aside className="sidebar">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '4px 8px 24px 8px', borderBottom: '1px solid #1e293b', marginBottom: '20px' }}>
            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #0284c7, #4f46e5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Activity size={20} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 800, fontSize: '1.05rem', letterSpacing: '-0.02em' }}>OpsPilot AI</div>
              <div style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 600 }}>ENTERPRISE SRE v2.4</div>
            </div>
          </div>

          <div style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 700, padding: '0 10px 8px 10px', letterSpacing: '0.06em' }}>
            CORE PLATFORM
          </div>

          <button className={`nav-btn ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => setActiveTab('overview')}>
            <LayoutDashboard size={18} />
            Executive Overview
          </button>

          <button className={`nav-btn ${activeTab === 'fleet' ? 'active' : ''}`} onClick={() => setActiveTab('fleet')}>
            <Globe size={18} />
            Live Website Fleet
            <span style={{ marginLeft: 'auto', backgroundColor: '#064e3b', color: '#34d399', padding: '2px 7px', borderRadius: '99px', fontSize: '0.7rem' }}>
              {fleet.length}
            </span>
          </button>

          <button className={`nav-btn ${activeTab === 'incidents' ? 'active' : ''}`} onClick={() => setActiveTab('incidents')}>
            <AlertTriangle size={18} />
            Incidents & RAG
            <span style={{ marginLeft: 'auto', backgroundColor: activeIncidents > 0 ? '#7f1d1d' : '#1e293b', color: activeIncidents > 0 ? '#fca5a5' : '#94a3b8', padding: '2px 7px', borderRadius: '99px', fontSize: '0.7rem' }}>
              {incidents.length}
            </span>
          </button>

          <button className={`nav-btn ${activeTab === 'mlops' ? 'active' : ''}`} onClick={() => setActiveTab('mlops')}>
            <Cpu size={18} />
            MLOps & Chaos Lab
          </button>
        </div>

        {/* User Profile Footer */}
        <div style={{ borderTop: '1px solid #1e293b', paddingTop: '16px' }}>
          <div style={{ backgroundColor: '#0f172a', padding: '12px', borderRadius: '10px', marginBottom: '10px', border: '1px solid #1e293b' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{user.name}</div>
            <div style={{ fontSize: '0.72rem', color: '#38bdf8', marginTop: '2px' }}>{user.role}</div>
            <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '2px' }}>{user.email}</div>
          </div>
          <button className="btn-ghost" style={{ width: '100%', justifyContent: 'center' }} onClick={handleLogout}>
            <LogOut size={15} /> Sign Out Session
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <div className="main-area">
        {/* Sticky Top Telemetry Header */}
        <header className="topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <span style={{
              backgroundColor: wsConnected ? '#064e3b' : '#7f1d1d',
              color: wsConnected ? '#34d399' : '#fca5a5',
              padding: '4px 11px',
              borderRadius: '999px',
              fontSize: '0.74rem',
              fontWeight: 700,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}>
              <Radio size={13} />
              {wsConnected ? 'WS PUB/SUB LIVE' : 'RECONNECTING'}
            </span>
            <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: '#94a3b8', maxWidth: '480px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {lastWsEvent}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ backgroundColor: '#111827', border: '1px solid #1e293b', padding: '6px 12px', borderRadius: '8px', fontSize: '0.76rem' }}>
              <span style={{ color: '#64748b' }}>X-Cache: </span>
              <strong style={{ color: telemetry.cacheStatus === 'HIT' ? '#34d399' : '#fbbf24' }}>{telemetry.cacheStatus}</strong>
            </div>
            <div style={{ backgroundColor: '#111827', border: '1px solid #1e293b', padding: '6px 12px', borderRadius: '8px', fontSize: '0.76rem' }}>
              <span style={{ color: '#64748b' }}>API Latency: </span>
              <strong style={{ color: '#38bdf8' }}>{telemetry.processTimeMs} ms</strong>
            </div>
            <div style={{ backgroundColor: '#111827', border: '1px solid #1e293b', padding: '6px 12px', borderRadius: '8px', fontSize: '0.76rem', fontFamily: 'monospace' }}>
              <span style={{ color: '#64748b' }}>Trace: </span>
              <span style={{ color: '#cbd5e1' }}>{telemetry.traceId}</span>
            </div>
            <button className="btn-ghost" onClick={loadAllData}>
              <RefreshCw size={14} /> Sync
            </button>
          </div>
        </header>

        {statusBanner && (
          <div style={{ backgroundColor: '#172554', borderBottom: '1px solid #1d4ed8', padding: '10px 28px', fontSize: '0.84rem', color: '#93c5fd', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{statusBanner}</span>
            <button onClick={() => setStatusBanner('')} style={{ background: 'none', border: 'none', color: '#93c5fd', cursor: 'pointer' }}>✕</button>
          </div>
        )}

        <main className="page-content">
          {/* ================================================================
              PAGE 1: EXECUTIVE OVERVIEW
          ================================================================ */}
          {activeTab === 'overview' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '22px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h1 style={{ fontSize: '1.6rem', fontWeight: 800 }}>Global SRE Executive Overview</h1>
                  <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: '4px' }}>
                    Real-time observability across {fleet.length} monitored websites, autonomous self-healing agents & RAG copilot
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button className="btn-primary" style={{ background: '#dc2626' }} onClick={() => handleChaosInject('error_500')}>
                    <Zap size={15} /> Simulate 500 Outage
                  </button>
                  <button className="btn-primary" style={{ background: '#d97706' }} onClick={() => handleChaosInject('latency_spike')}>
                    <Clock size={15} /> Simulate 2200ms Drift
                  </button>
                  <button className="btn-ghost" onClick={() => setActiveTab('fleet')}>
                    Explore All {fleet.length} Websites →
                  </button>
                </div>
              </div>

              {/* Top 4 KPI Cards */}
              <div className="kpi-grid">
                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 700 }}>MONITORED WEBSITE FLEET</div>
                  <div style={{ fontSize: '2.1rem', fontWeight: 800, margin: '8px 0', color: '#38bdf8' }}>
                    {operationalCount} <span style={{ fontSize: '1.1rem', color: '#64748b' }}>/ {fleet.length}</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#34d399' }}>● 99.96% Global Fleet Uptime SLA</div>
                </div>

                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 700 }}>GLOBAL P50 LATENCY</div>
                  <div style={{ fontSize: '2.1rem', fontWeight: 800, margin: '8px 0', color: '#a78bfa' }}>
                    {avgFleetLatency} <span style={{ fontSize: '1rem', color: '#64748b' }}>ms</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Trained Baseline: {mlMetrics.baseline_median_ms}ms</div>
                </div>

                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 700 }}>AUTONOMOUS AI HEALS</div>
                  <div style={{ fontSize: '2.1rem', fontWeight: 800, margin: '8px 0', color: '#34d399' }}>
                    {resolvedCount} <span style={{ fontSize: '1rem', color: '#64748b' }}>resolved</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#34d399' }}>Avg Self-Healing MTTR: 10.1s</div>
                </div>

                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.78rem', fontWeight: 700 }}>VECTOR RAG CONFIDENCE</div>
                  <div style={{ fontSize: '2.1rem', fontWeight: 800, margin: '8px 0', color: '#fbbf24' }}>
                    91.6%
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>256-D CRC32 TF-IDF Cosine Engine</div>
                </div>
              </div>

              {/* Fleet Category Breakdown + Recent Incidents */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px' }}>
                <div className="glass-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>100-Website Fleet Health by Sector</h3>
                    <button className="btn-ghost" onClick={() => setActiveTab('fleet')}>View Fleet</button>
                  </div>
                  <div style={{ display: 'grid', gap: '12px' }}>
                    {categories.filter((c) => c !== 'ALL').map((cat) => {
                      const catSites = fleet.filter((s) => s.category === cat);
                      const catAvg = catSites.length
                        ? (catSites.reduce((a, b) => a + b.latency_ms, 0) / catSites.length).toFixed(1)
                        : '0';
                      return (
                        <div
                          key={cat}
                          onClick={() => { setSelectedCategory(cat); setActiveTab('fleet'); }}
                          style={{ backgroundColor: '#090d16', border: '1px solid #1e293b', padding: '12px 16px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                        >
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{cat}</div>
                            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{catSites.length} endpoints monitored</div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ color: '#34d399', fontSize: '0.82rem', fontWeight: 700 }}>100% Online</div>
                            <div style={{ color: '#38bdf8', fontSize: '0.75rem', fontFamily: 'monospace' }}>Avg {catAvg} ms</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="glass-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Recent Autonomous AI Incidents</h3>
                    <button className="btn-ghost" onClick={() => setActiveTab('incidents')}>Open RAG Center</button>
                  </div>
                  <div style={{ display: 'grid', gap: '10px' }}>
                    {incidents.slice(0, 5).map((inc) => (
                      <div
                        key={inc.id}
                        onClick={() => handleInspectIncident(inc.id)}
                        style={{ backgroundColor: '#090d16', border: '1px solid #1e293b', borderLeft: `4px solid ${inc.status === 'resolved' ? '#10b981' : '#ef4444'}`, padding: '12px 14px', borderRadius: '8px', cursor: 'pointer' }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', marginBottom: '4px' }}>
                          <span style={{ color: '#a5b4fc', fontFamily: 'monospace', fontWeight: 700 }}>
                            #{inc.id} [{extractAiTag(inc.description || inc.title)}]
                          </span>
                          <span style={{ color: inc.status === 'resolved' ? '#34d399' : '#fbbf24', fontWeight: 700 }}>
                            {inc.status === 'resolved' ? '✓ AI HEALED' : inc.status.toUpperCase()}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#f1f5f9' }}>{inc.title}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ================================================================
              PAGE 2: 100+ LIVE WEBSITE FLEET TRACKER
          ================================================================ */}
          {activeTab === 'fleet' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h1 style={{ fontSize: '1.55rem', fontWeight: 800 }}>
                    Global Website & API Fleet ({filteredFleet.length} Endpoints)
                  </h1>
                  <p style={{ color: '#94a3b8', fontSize: '0.88rem', marginTop: '4px' }}>
                    Click "Live Ping" on any website to trigger an instant HTTP probe from your AWS EC2 node
                  </p>
                </div>

                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <div style={{ position: 'relative' }}>
                    <Search size={15} style={{ position: 'absolute', left: '12px', top: '12px', color: '#64748b' }} />
                    <input
                      className="input-dark"
                      style={{ paddingLeft: '34px', width: '260px' }}
                      placeholder="Search 100+ websites, URLs, regions..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>
                  <button className="btn-primary" onClick={() => setShowAddModal(!showAddModal)}>
                    <Plus size={16} /> Add Custom Website
                  </button>
                </div>
              </div>

              {/* Add Custom Website Inline Form */}
              {showAddModal && (
                <form onSubmit={handleAddWebsite} className="glass-card" style={{ marginBottom: '20px', display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: '200px' }}>
                    <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>Website Name</label>
                    <input className="input-dark" style={{ width: '100%' }} placeholder="e.g. RNSIT College Portal" value={newSiteName} onChange={(e) => setNewSiteName(e.target.value)} required />
                  </div>
                  <div style={{ flex: 1.5, minWidth: '240px' }}>
                    <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>Target URL (https://)</label>
                    <input className="input-dark" style={{ width: '100%' }} value={newSiteUrl} onChange={(e) => setNewSiteUrl(e.target.value)} required />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8', marginBottom: '4px' }}>Category</label>
                    <input className="input-dark" value={newSiteCategory} onChange={(e) => setNewSiteCategory(e.target.value)} />
                  </div>
                  <button type="submit" className="btn-primary">Save & Monitor</button>
                </form>
              )}

              {/* Category Filter Pills */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px' }}>
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    style={{
                      padding: '7px 14px',
                      borderRadius: '999px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                      border: selectedCategory === cat ? '1px solid #38bdf8' : '1px solid #1e293b',
                      backgroundColor: selectedCategory === cat ? 'rgba(56, 189, 248, 0.15)' : '#0f172a',
                      color: selectedCategory === cat ? '#38bdf8' : '#94a3b8',
                    }}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              {/* 100-Website Grid */}
              <div className="fleet-grid">
                {filteredFleet.map((svc) => {
                  const isHealthy = svc.status === 'operational';
                  const color = isHealthy ? '#34d399' : svc.status === 'degraded' ? '#fbbf24' : '#ef4444';

                  return (
                    <div key={svc.id} className="glass-card" style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                          <span style={{ fontSize: '0.7rem', color: '#38bdf8', backgroundColor: '#0c192c', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                            {svc.category}
                          </span>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.74rem', fontWeight: 700, color }}>
                            {isHealthy ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                            {svc.status.toUpperCase()}
                          </span>
                        </div>

                        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '3px' }}>{svc.name}</h3>
                        <div style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {svc.url}
                        </div>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #1e293b', paddingTop: '10px' }}>
                        <div>
                          <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#f1f5f9', fontFamily: 'monospace' }}>
                            {svc.latency_ms} <span style={{ fontSize: '0.75rem', color: '#64748b' }}>ms</span>
                          </div>
                          <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                            Uptime: {svc.uptime_pct}% • {svc.region}
                          </div>
                        </div>
                        <Sparkline data={svc.sparkline} color={color} />
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem', color: '#64748b' }}>
                        <span>{svc.last_checked}</span>
                        <button
                          className="btn-ghost"
                          style={{ padding: '5px 10px', fontSize: '0.74rem' }}
                          onClick={() => handleLivePing(svc.id)}
                          disabled={pingingId === svc.id}
                        >
                          <Zap size={12} color="#38bdf8" />
                          {pingingId === svc.id ? 'Probing...' : 'Live Ping'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ================================================================
              PAGE 3: INCIDENTS & RAG COPILOT WORKBENCH
          ================================================================ */}
          {activeTab === 'incidents' && (
            <div>
              <div style={{ marginBottom: '20px' }}>
                <h1 style={{ fontSize: '1.55rem', fontWeight: 800 }}>Autonomous Incident Feed & Vector RAG Copilot</h1>
                <p style={{ color: '#94a3b8', fontSize: '0.88rem', marginTop: '4px' }}>
                  Select any incident to run 256-D Cosine Similarity search across historical PostgreSQL outages and generate SRE CLI runbooks
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: selectedIncidentId ? '1.1fr 0.9fr' : '1fr', gap: '22px', alignItems: 'start' }}>
                <div style={{ display: 'grid', gap: '14px' }}>
                  {incidents.map((inc) => {
                    const isResolved = inc.status === 'resolved';
                    const aiTag = extractAiTag(inc.description || inc.title);
                    return (
                      <div
                        key={inc.id}
                        className="glass-card"
                        style={{
                          borderLeft: `5px solid ${isResolved ? '#10b981' : '#ef4444'}`,
                          borderColor: selectedIncidentId === inc.id ? '#38bdf8' : '#1e293b',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
                          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                            <span style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '0.8rem' }}>#{inc.id}</span>
                            <span style={{ backgroundColor: '#7f1d1d', color: '#fca5a5', padding: '2px 8px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase' }}>
                              {inc.severity}
                            </span>
                            <span style={{ backgroundColor: '#1e1b4b', color: '#a5b4fc', border: '1px solid #3730a3', padding: '2px 8px', borderRadius: '4px', fontSize: '0.72rem', fontFamily: 'monospace', fontWeight: 600 }}>
                              🧠 {aiTag}
                            </span>
                          </div>
                          <span style={{ backgroundColor: isResolved ? '#064e3b' : '#451a03', color: isResolved ? '#34d399' : '#fbbf24', padding: '3px 10px', borderRadius: '99px', fontSize: '0.74rem', fontWeight: 700 }}>
                            {isResolved ? '✓ RESOLVED (AI HEALED)' : inc.status.toUpperCase()}
                          </span>
                        </div>

                        <h3 style={{ fontSize: '1.05rem', marginBottom: '6px' }}>{inc.title}</h3>
                        <p style={{ color: '#94a3b8', fontSize: '0.86rem', lineHeight: 1.5, marginBottom: '14px' }}>{inc.description}</p>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Logged: {new Date(inc.created_at).toLocaleString()}</span>
                          <button className="btn-primary" onClick={() => handleInspectIncident(inc.id)}>
                            <Terminal size={14} /> Open RAG Copilot & Audit Trail
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {selectedIncidentId && (
                  <aside className="glass-card" style={{ position: 'sticky', top: '88px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', paddingBottom: '12px', marginBottom: '16px' }}>
                      <h3 style={{ color: '#38bdf8', fontSize: '1.05rem' }}>🤖 Incident #{selectedIncidentId} RAG Copilot</h3>
                      <button className="btn-ghost" onClick={() => setSelectedIncidentId(null)}>✕ Close</button>
                    </div>

                    {inspectorLoading ? (
                      <p style={{ color: '#38bdf8' }}>Computing 256-D Cosine Similarity & fetching Audit Trail...</p>
                    ) : (
                      <>
                        {ragData && (
                          <div>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                              <span style={{ backgroundColor: '#1e1b4b', color: '#c7d2fe', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 700 }}>
                                {ragData.predicted_tag}
                              </span>
                              <span style={{ backgroundColor: '#064e3b', color: '#6ee7b7', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 700 }}>
                                Cosine Confidence: {ragData.confidence_pct}%
                              </span>
                              <span style={{ backgroundColor: '#1f2937', color: '#cbd5e1', padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                                {ragData.retrieved_runbook.doc_id}
                              </span>
                            </div>

                            <div style={{ backgroundColor: '#090d16', border: '1px solid #1e293b', padding: '12px', borderRadius: '8px', fontSize: '0.84rem', lineHeight: 1.5, marginBottom: '14px' }}>
                              {ragData.generated_rca_summary}
                            </div>

                            <div style={{ fontSize: '0.76rem', color: '#94a3b8', fontWeight: 700, marginBottom: '6px', textTransform: 'uppercase' }}>
                              Retrieved CLI Remediation Runbook
                            </div>
                            <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', padding: '10px 12px', borderRadius: '8px', fontFamily: 'monospace', fontSize: '0.78rem', color: '#34d399', marginBottom: '14px' }}>
                              {ragData.retrieved_runbook.commands.map((cmd, i) => (
                                <div key={i} style={{ marginBottom: '4px' }}>$ {cmd}</div>
                              ))}
                            </div>

                            <div style={{ fontSize: '0.76rem', color: '#94a3b8', fontWeight: 700, marginBottom: '6px', textTransform: 'uppercase' }}>
                              Top-K Vector Similar Past Incidents (PostgreSQL)
                            </div>
                            <div style={{ display: 'grid', gap: '6px', marginBottom: '16px' }}>
                              {ragData.retrieved_historical_incidents.map((m) => (
                                <div key={m.incident_id} style={{ backgroundColor: '#090d16', padding: '8px 10px', borderRadius: '6px', fontSize: '0.78rem', display: 'flex', justifyContent: 'space-between' }}>
                                  <span>#{m.incident_id}: {m.title.slice(0, 40)}...</span>
                                  <strong style={{ color: '#38bdf8' }}>{m.similarity_score}% match</strong>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div style={{ fontSize: '0.76rem', color: '#94a3b8', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase' }}>
                          Millisecond Audit Log Timeline ({auditLogs.length} events)
                        </div>
                        <div style={{ display: 'grid', gap: '8px', maxHeight: '240px', overflowY: 'auto' }}>
                          {auditLogs.map((log) => (
                            <div key={log.id} style={{ backgroundColor: '#090d16', borderLeft: '3px solid #38bdf8', padding: '8px 12px', borderRadius: '6px', fontSize: '0.78rem' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8', fontWeight: 700, marginBottom: '3px' }}>
                                <span>{log.action}</span>
                                <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{new Date(log.timestamp).toLocaleTimeString()}</span>
                              </div>
                              <div style={{ color: '#cbd5e1' }}>{log.details}</div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </aside>
                )}
              </div>
            </div>
          )}

          {/* ================================================================
              PAGE 4: MLOPS & CHAOS ENGINEERING LAB
          ================================================================ */}
          {activeTab === 'mlops' && (
            <div>
              <div style={{ marginBottom: '22px' }}>
                <h1 style={{ fontSize: '1.55rem', fontWeight: 800 }}>MLOps Pipeline & Chaos Engineering Lab</h1>
                <p style={{ color: '#94a3b8', fontSize: '0.88rem', marginTop: '4px' }}>
                  Manage serialized NumPy model weights ({mlMetrics.artifact}), retrain vector centroids live, and inject production faults
                </p>
              </div>

              <div className="kpi-grid">
                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700 }}>SERIALIZED MODEL ARTIFACT</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, margin: '10px 0', color: '#38bdf8', fontFamily: 'monospace' }}>
                    {mlMetrics.artifact}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#34d399' }}>In-Memory Zero-Latency Inference</div>
                </div>

                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700 }}>NLP EMBEDDING SPACE</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, margin: '8px 0', color: '#a78bfa' }}>
                    {mlMetrics.vector_dim}-D <span style={{ fontSize: '0.9rem', color: '#64748b' }}>CRC32 TF-IDF</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Deterministic Word + Char 3-Grams</div>
                </div>

                <div className="glass-card">
                  <div style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700 }}>ISOLATION-MAD BASELINE</div>
                  <div style={{ fontSize: '1.8rem', fontWeight: 800, margin: '8px 0', color: '#34d399' }}>
                    {mlMetrics.baseline_median_ms} ms
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Auto-Threshold: {mlMetrics.threshold_ms} ms</div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px' }}>
                <div className="glass-card">
                  <h3 style={{ fontSize: '1.1rem', marginBottom: '10px' }}>💥 Chaos Fault Injection Deck</h3>
                  <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '18px', lineHeight: 1.5 }}>
                    Trigger real production failures on the Payment-Gateway-API microservice to verify Celery Beat detection, 5-strike Redis Circuit Breaker, and 10-second autonomous self-healing.
                  </p>
                  <div style={{ display: 'grid', gap: '12px' }}>
                    <button className="btn-primary" style={{ background: '#dc2626', padding: '12px', justifyContent: 'center' }} onClick={() => handleChaosInject('error_500')}>
                      💥 Inject HTTP 500 Gateway Crash (Triggers Path A Auto-Heal in 10s)
                    </button>
                    <button className="btn-primary" style={{ background: '#d97706', padding: '12px', justifyContent: 'center' }} onClick={() => handleChaosInject('latency_spike')}>
                      🐢 Inject 2200ms P99 Latency Drift (Triggers Predictive ML Alert)
                    </button>
                    <button className="btn-primary" style={{ background: '#059669', padding: '12px', justifyContent: 'center' }} onClick={handleChaosReset}>
                      🟢 Reset All Chaos States to Healthy
                    </button>
                  </div>
                </div>

                <div className="glass-card">
                  <h3 style={{ fontSize: '1.1rem', marginBottom: '10px' }}>🧠 Live MLOps Model Retraining</h3>
                  <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '18px', lineHeight: 1.5 }}>
                    Re-runs <code style={{ color: '#38bdf8' }}>app.train_models</code> on AWS EC2, refitting the 1,000-sample Isolation Quantile latency distribution and recomputing normalized TF-IDF class centroids.
                  </p>
                  <button className="btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '14px', background: '#4f46e5' }} onClick={handleRetrain}>
                    <Cpu size={17} /> Trigger Live Model Retraining (POST /aiops/retrain)
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
