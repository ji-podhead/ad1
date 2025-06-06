// Simple calendar component for date selection
import React from 'react';

interface CalendarProps {
  value: string;
  onChange: (date: string) => void;
  mode?: 'day' | 'week' | 'month';
}

function getCurrentISOWeek() {
  const now = new Date();
  const onejan = new Date(now.getFullYear(),0,1);
  const week = Math.ceil((((now.getTime() - onejan.getTime()) / 86400000) + onejan.getDay()+1)/7);
  return `${now.getFullYear()}-W${week.toString().padStart(2, '0')}`;
}

const Calendar: React.FC<CalendarProps> = ({ value, onChange, mode = 'day' }) => {
  if (mode === 'week') {
    return (
      <input
        type="week"
        className="border rounded px-3 py-2"
        value={value}
        onChange={e => onChange(e.target.value)}
        max={getCurrentISOWeek()}
      />
    );
  }
  if (mode === 'month') {
    return (
      <input
        type="month"
        className="border rounded px-3 py-2"
        value={value}
        onChange={e => onChange(e.target.value)}
        max={new Date().toISOString().slice(0, 7)}
      />
    );
  }
  // default: day
  return (
    <input
      type="date"
      className="border rounded px-3 py-2"
      value={value}
      onChange={e => onChange(e.target.value)}
      max={new Date().toISOString().slice(0, 10)}
    />
  );
};

export default Calendar;
