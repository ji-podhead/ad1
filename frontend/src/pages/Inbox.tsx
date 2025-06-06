// Inbox page: List, filter, and label emails. Trigger workflows on incoming emails. See processing status.
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import EmailModal from '../components/EmailModal';

interface Email {
  id: number;
  subject: string;
  from: string;
  status: string;
  date: string;
  documents: string[];
  body: string;
}

const Inbox: React.FC = () => {
  const [filter, setFilter] = useState('All');
  const [hovered, setHovered] = useState<number|null>(null);
  const [modalEmail, setModalEmail] = useState<Email|null>(null);
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string|null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchEmails = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/emails');
        if (!response.ok) throw new Error('Failed to fetch emails');
        const data = await response.json();
        // Map backend data to Email interface if needed
        setEmails(data.map((item: any) => ({
          id: item.id,
          subject: item.subject,
          from: item.sender,
          status: item.status || 'Pending',
          date: item.received_at ? new Date(item.received_at).toISOString().slice(0, 10) : '',
          documents: item.documents || [],
          body: item.body || '',
        })));
      } catch (err: any) {
        setError(err.message || 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    fetchEmails();
  }, []);

  const filtered = filter === 'All' ? emails : emails.filter(e => e.status === filter);

  if (loading) return <div className="p-6 text-center">{emails.length === 0 ? 'Keine E-Mails vorhanden.' : 'Loading emails...'}</div>;
  if (error) return <div className="p-6 text-center text-red-500">Error: {error}</div>;

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
            <th className="p-2 text-left">Documents</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(email => (
            <tr key={email.id} className="border-t group relative">
              <td
                className="p-2 cursor-pointer text-blue-700 hover:underline relative"
                onMouseEnter={() => setHovered(email.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setModalEmail(email)}
              >
                {email.subject}
                {hovered === email.id && (
                  <div className="absolute left-0 top-full mt-1 z-30 bg-white border rounded shadow-lg p-3 w-72 text-xs animate-fade-in-up">
                    <div className="font-bold mb-1">{email.subject}</div>
                    <div className="mb-1 text-gray-500">From: {email.from}</div>
                    <div className="mb-1 text-gray-400">{email.date}</div>
                    <div className="text-gray-700 whitespace-pre-line">{email.body.slice(0, 120)}...</div>
                  </div>
                )}
              </td>
              <td className="p-2">{email.from}</td>
              <td className="p-2">{email.date}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${email.status === 'Pending' ? 'bg-yellow-200' : email.status === 'Processing' ? 'bg-blue-200' : 'bg-green-200'}`}>{email.status}</span>
              </td>
              <td className="p-2">
                {email.documents && email.documents.map((doc: string, i: number) => (
                  <span
                    key={i}
                    className="inline-block bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs mr-1 mb-1 cursor-pointer hover:bg-blue-100 hover:underline"
                    onClick={() => navigate(`/documents?doc=${encodeURIComponent(doc)}`)}
                  >
                    {doc}
                  </span>
                ))}
              </td>
              <td className="p-2 flex gap-2">
                <button className="bg-blue-500 text-white px-2 py-1 rounded text-xs">Trigger Workflow</button>
                <button className="bg-gray-300 text-gray-800 px-2 py-1 rounded text-xs">Label</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <EmailModal open={!!modalEmail} onClose={() => setModalEmail(null)} email={modalEmail} />
    </div>
  );
};

export default Inbox;
