import React from 'react';

const TONE = {
  blue: 'bg-blue-100 text-blue-700',
  red: 'bg-red-100 text-red-700',
  green: 'bg-green-100 text-green-700',
  yellow: 'bg-yellow-100 text-yellow-700',
};

const MetricCard = ({ title, value, change, color = 'blue' }) => {
  const tone = TONE[color] ?? TONE.blue;
  return (
    <div className="bg-white rounded-lg shadow p-6 flex flex-col space-y-3">
      <div className="text-sm font-medium text-gray-500 uppercase tracking-wide">{title}</div>
      <div className="text-3xl font-semibold text-gray-900">{value}</div>
      {change ? (
        <span className={`inline-flex w-fit items-center text-xs font-medium px-2 py-1 rounded ${tone}`}>
          {change}
        </span>
      ) : null}
    </div>
  );
};

export default MetricCard;
