import React, { useMemo } from 'react';
import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const PerformanceCharts = ({ history, fraudSplit }) => {
  const labels = history.map((entry) => entry.timestamp);

  const throughputData = useMemo(() => ({
    labels,
    datasets: [
      {
        label: 'Transactions / Second',
        data: history.map((entry) => entry.transactions_per_second ?? 0),
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.2)',
        tension: 0.3,
        fill: true,
      },
      {
        label: 'Fraud Detected',
        data: history.map((entry) => entry.fraud_detected ?? 0),
        borderColor: '#EF4444',
        backgroundColor: 'rgba(239, 68, 68, 0.2)',
        tension: 0.3,
        fill: true,
      },
    ],
  }), [history, labels]);

  const fraudPatternData = useMemo(() => ({
    labels: ['Legit', 'Fraud'],
    datasets: [
      {
        data: [Math.max(fraudSplit.legit, 0), Math.max(fraudSplit.fraud, 0)],
        backgroundColor: ['#10B981', '#EF4444'],
        hoverOffset: 4,
      },
    ],
  }), [fraudSplit]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Performance Trend</h2>
        <Line
          data={throughputData}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: { beginAtZero: true },
            },
            plugins: {
              legend: { position: 'bottom' },
            },
          }}
          height={320}
        />
      </div>
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Fraud Split</h2>
        <div className="h-80 flex items-center justify-center">
          <Doughnut
            data={fraudPatternData}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { position: 'bottom' },
              },
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default PerformanceCharts;
