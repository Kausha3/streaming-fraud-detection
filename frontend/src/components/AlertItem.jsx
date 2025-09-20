import React from 'react';

const AlertItem = ({ alert }) => {
  if (!alert) return null;
  const score = alert.fraud_detection?.fraud_score ?? alert.fraud_score ?? 0;

  return (
    <div className="p-3 border border-red-200 bg-red-50 rounded">
      <div className="flex justify-between items-center">
        <span className="text-sm font-semibold text-red-700">
          {(alert.transaction_id || '----------').slice(0, 8)}
        </span>
        <span className="text-xs font-semibold text-red-600">
          {(score * 100).toFixed(0)}%
        </span>
      </div>
      <p className="text-xs text-red-600 mt-1">
        {alert.user_id || 'Unknown user'} · ${Number(alert.amount ?? 0).toFixed(2)} · {alert.location || 'N/A'}
      </p>
      <p className="text-xs text-red-500 mt-1">
        {alert.fraud_detection?.explanation?.reason || alert.explanation?.reason || 'Potential fraud detected'}
      </p>
    </div>
  );
};

export default AlertItem;
