import React, { useEffect, useMemo, useState } from 'react';
import MetricCard from './components/MetricCard.jsx';
import TransactionItem from './components/TransactionItem.jsx';
import AlertItem from './components/AlertItem.jsx';
import PerformanceCharts from './components/PerformanceCharts.jsx';

const STATS_INTERVAL_MS = 5000;
const LIVE_LIMIT = 50;
const ALERT_LIMIT = 10;

const App = () => {
  const [stats, setStats] = useState(null);
  const [statsHistory, setStatsHistory] = useState([]);
  const [liveTransactions, setLiveTransactions] = useState([]);
  const [fraudAlerts, setFraudAlerts] = useState([]);
  const [wsStatus, setWsStatus] = useState('connecting');

  useEffect(() => {
    let active = true;

    const fetchStats = async () => {
      try {
        const response = await fetch('/api/v1/stats/overview');
        if (!response.ok) {
          throw new Error(`Status ${response.status}`);
        }
        const payload = await response.json();
        if (!active) return;
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setStats(payload);
        setStatsHistory((prev) => {
          const next = [...prev, { ...payload, timestamp }];
          return next.slice(-24);
        });
      } catch (error) {
        console.error('Failed to fetch stats', error);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, STATS_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const socket = new WebSocket(`${protocol}://${host}/ws/live`);

    socket.onopen = () => setWsStatus('connected');
    socket.onclose = () => setWsStatus('closed');
    socket.onerror = () => setWsStatus('error');

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        setLiveTransactions((prev) => {
          const next = [normalizeTransaction(payload), ...prev];
          return next.slice(0, LIVE_LIMIT);
        });
        const isFraud = payload?.fraud_detection?.is_fraud ?? payload?.is_fraud;
        if (isFraud) {
          setFraudAlerts((prev) => {
            const next = [normalizeTransaction(payload), ...prev];
            return next.slice(0, ALERT_LIMIT);
          });
        }
      } catch (error) {
        console.error('Error parsing websocket payload', error);
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  const fraudSplit = useMemo(() => {
    if (!stats) return { legit: 1, fraud: 0 };
    const total = Number(stats.total_transactions ?? 0);
    const fraud = Number(stats.fraud_detected ?? 0);
    return {
      legit: Math.max(total - fraud, 0),
      fraud,
    };
  }, [stats]);

  const metrics = useMemo(() => ({
    tps: stats?.transactions_per_second ?? 0,
    fraudAmount: stats?.fraud_prevented_amount ?? 0,
    accuracy: stats?.detection_accuracy ?? 0,
    latency: stats?.avg_processing_time_ms ?? 0,
  }), [stats]);

  return (
    <div className="min-h-screen bg-gray-100">
      <main className="max-w-7xl mx-auto px-6 py-10 space-y-8">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-800">Fraud Detection Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">Streaming insights refreshed in real time.</p>
          </div>
          <StatusBadge status={wsStatus} />
        </header>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <MetricCard title="Transactions / Second" value={metrics.tps.toFixed(2)} change="+12%" color="blue" />
          <MetricCard title="Fraud Prevented" value={`$${(metrics.fraudAmount / 1_000_000).toFixed(2)}M`} change="-8%" color="red" />
          <MetricCard title="Detection Accuracy" value={`${(metrics.accuracy * 100).toFixed(1)}%`} change="+2%" color="green" />
          <MetricCard title="Avg Latency" value={`${metrics.latency.toFixed(0)}ms`} change="-15%" color="yellow" />
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow p-6 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">Live Transactions</h2>
              <span className="text-xs text-gray-500">Latest {liveTransactions.length}</span>
            </div>
            <div className="space-y-3 overflow-y-auto" style={{ maxHeight: '24rem' }}>
              {liveTransactions.length === 0 ? (
                <EmptyState message="Waiting for transactions..." />
              ) : (
                liveTransactions.map((tx) => (
                  <TransactionItem key={tx.transaction_id + tx.timestamp} transaction={tx} />
                ))
              )}
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6 flex flex-col">
            <h2 className="text-lg font-semibold text-red-600 mb-4">Fraud Alerts</h2>
            <div className="space-y-3 overflow-y-auto" style={{ maxHeight: '24rem' }}>
              {fraudAlerts.length === 0 ? (
                <EmptyState message="No active alerts" variant="alert" />
              ) : (
                fraudAlerts.map((alert) => (
                  <AlertItem key={alert.transaction_id + alert.timestamp} alert={alert} />
                ))
              )}
            </div>
          </div>
        </section>

        <PerformanceCharts history={statsHistory} fraudSplit={fraudSplit} />
      </main>
    </div>
  );
};

const normalizeTransaction = (payload) => ({
  transaction_id: payload.transaction_id ?? safeUUID(),
  amount: payload.amount ?? payload.fraud_detection?.amount ?? 0,
  merchant: payload.merchant ?? payload.fraud_detection?.merchant ?? 'Unknown',
  location: payload.location ?? payload.fraud_detection?.location ?? 'Unknown',
  fraud_detection: payload.fraud_detection ?? payload,
  fraud_score: payload.fraud_score,
  is_fraud: payload.is_fraud,
  user_id: payload.user_id,
  timestamp: payload.timestamp ?? new Date().toISOString(),
});

const StatusBadge = ({ status }) => {
  const palette = {
    connected: { label: 'Live', className: 'bg-green-100 text-green-700' },
    connecting: { label: 'Connecting', className: 'bg-yellow-100 text-yellow-700' },
    error: { label: 'Error', className: 'bg-red-100 text-red-700' },
    closed: { label: 'Disconnected', className: 'bg-gray-200 text-gray-600' },
  };
  const state = palette[status] ?? palette.connecting;
  return <span className={`px-3 py-1 rounded text-xs font-medium ${state.className}`}>{state.label}</span>;
};

const EmptyState = ({ message, variant = 'default' }) => {
  const tone =
    variant === 'alert'
      ? 'border border-red-200 bg-red-50 text-red-600'
      : 'border border-dashed border-gray-200 text-gray-500';
  return (
    <div className={`p-6 text-center text-sm rounded ${tone}`}>
      {message}
    </div>
  );
};

export default App;

function safeUUID() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `tx-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}
