// Inbox page: List, filter, and label emails. Trigger workflows on incoming emails. See processing status.
import React, { useState } from 'react';

const demoEmails = [
  { id: 1, subject: 'New Registration Form', from: 'office@agency.ch', status: 'Pending', date: '2025-06-03' },
  { id: 2, subject: 'Case Update', from: 'caseworker@org.ch', status: 'Processing', date: '2025-06-02' },
  { id: 3, subject: 'Final Report', from: 'admin@org.ch', status: 'Validated', date: '2025-06-01' },
];

const Inbox: React.FC = () => {
  const [filter, setFilter] = useState('All');
  const filtered = filter === 'All' ? demoEmails : demoEmails.filter(e => e.status === filter);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Inbox</h1>
      <div className="mb-4 flex gap-2">
        <label>Status Filter:</label>
        <select value={filter} onChange={e => setFilter(e.target.value)} className="border rounded px-2 py-1">
          <option>All</option>
          <option>Pending</option>
          <option>Processing</option>
          <option>Validated</option>
        </select>
      </div>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Subject</th>
            <th className="p-2 text-left">From</th>
            <th className="p-2 text-left">Date</th>
            <th className="p-2 text-left">Status</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(email => (
            <tr key={email.id} className="border-t">
              <td className="p-2">{email.subject}</td>
              <td className="p-2">{email.from}</td>
              <td className="p-2">{email.date}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${email.status === 'Pending' ? 'bg-yellow-200' : email.status === 'Processing' ? 'bg-blue-200' : 'bg-green-200'}`}>{email.status}</span>
              </td>
              <td className="p-2 flex gap-2">
                <button className="bg-blue-500 text-white px-2 py-1 rounded text-xs">Trigger Workflow</button>
                <button className="bg-gray-300 text-gray-800 px-2 py-1 rounded text-xs">Label</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Inbox;
