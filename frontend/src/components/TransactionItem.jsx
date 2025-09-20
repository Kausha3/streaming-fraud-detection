import React from 'react';

const TransactionItem = ({ transaction }) => {
  if (!transaction) return null;

  const score = transaction.fraud_detection?.fraud_score ?? transaction.fraud_score ?? 0;
  const isFraud = transaction.fraud_detection?.is_fraud ?? transaction.is_fraud ?? score > 0.5;
  const badgeClass = isFraud ? 'bg-red-500' : 'bg-green-500';
  const textClass = isFraud ? 'text-red-600' : 'text-green-600';

  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded">
      <div className="flex items-center space-x-3">
        <span className={`w-2 h-2 rounded-full ${badgeClass}`} aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-gray-800">
            {(transaction.transaction_id || '----------').slice(0, 8)}
          </p>
          <p className="text-xs text-gray-500">
            ${Number(transaction.amount ?? 0).toFixed(2)} · {transaction.merchant || 'Unknown'}
          </p>
        </div>
      </div>
      <div className="text-right">
        <p className="text-xs text-gray-500">{transaction.location || 'N/A'}</p>
        <p className={`text-xs font-semibold ${textClass}`}>
          Score: {(score * 100).toFixed(0)}%
        </p>
      </div>
    </div>
  );
};

export default TransactionItem;
