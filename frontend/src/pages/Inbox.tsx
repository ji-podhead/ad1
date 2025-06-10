// Inbox page: List, filter, and label emails. Trigger workflows on incoming emails. See processing status.
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import EmailModal from '../components/EmailModal';

interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  thumbnail_base64?: string; // For image hover previews
}

interface Email {
  id: number;
  subject: string;
  from: string;
  status: string;
  date: string;
  attachments: Attachment[];
  body: string;
}

const Inbox: React.FC = () => {
  const [filter, setFilter] = useState('All');
  const [hoveredEmailId, setHoveredEmailId] = useState<number | null>(null); // Renamed from hovered
  const [modalEmail, setModalEmail] = useState<Email | null>(null);
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const [hoveredAttachmentPreview, setHoveredAttachmentPreview] = useState<{
    x: number;
    y: number;
    attachment: Attachment;
  } | null>(null);

  useEffect(() => {
    const fetchEmails = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/emails');
        if (!response.ok) throw new Error('Failed to fetch emails');
        const apiData = await response.json();
        console.log(apiData)
        // Assume apiData is an array of email objects from the backend
        // Each email object should have an 'attachments' array like:
        // { id: number, filename: string, content_type: string, thumbnail_base64?: string }
        setEmails(apiData.map((item: any) => ({
          id: item.id,
          subject: item.subject,
          from: item.sender, // Assuming 'sender' field from backend
          status: item.status || 'Pending',
          date: item.received_at ? new Date(item.received_at).toLocaleDateString() : 'N/A', // Format date
          attachments: item.attachments || [], // Ensure this matches backend response structure
          body: item.body || '',
        })));
        console.log("Fetched emails:", apiData);
      } catch (err: any) {
        setError(err.message || 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    fetchEmails();
  }, []);

  const handleAttachmentHover = (e: React.MouseEvent, attachment: Attachment) => {
    setHoveredAttachmentPreview({ x: e.clientX, y: e.clientY, attachment });
  };

  const clearAttachmentHover = () => {
    setHoveredAttachmentPreview(null);
  };

  const filtered = filter === 'All' ? emails : emails.filter(e => e.status === filter);

  if (loading && emails.length === 0) return <div className="p-6 text-center">Loading emails...</div>;
  if (error) return <div className="p-6 text-center text-red-500">Error: {error}</div>;
  if (!loading && emails.length === 0) return <div className="p-6 text-center">No emails found.</div>;

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
            <th className="p-2 text-left">Attachments</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(email => (
            <tr key={email.id} className="border-t group relative">
              <td
                className="p-2 cursor-pointer text-blue-700 hover:underline relative"
                onMouseEnter={() => setHoveredEmailId(email.id)}
                onMouseLeave={() => setHoveredEmailId(null)}
                onClick={() => setModalEmail(email)}
              >
                {email.subject}
                {hoveredEmailId === email.id && (
                  <div className="absolute left-0 top-full mt-1 z-30 bg-white border rounded shadow-lg p-3 w-72 text-xs animate-fade-in-up">
                    <div className="font-bold mb-1">{email.subject}</div>
                    <div className="mb-1 text-gray-500">From: {email.from}</div>
                    <div className="mb-1 text-gray-400">Date: {email.date}</div>
                    <div className="text-gray-700 whitespace-pre-line">{(email.body || '').slice(0, 120)}...</div>
                  </div>
                )}
              </td>
              <td className="p-2">{email.from}</td>
              <td className="p-2">{email.date}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${email.status === 'Pending' ? 'bg-yellow-200 text-yellow-800' : email.status === 'Processing' ? 'bg-blue-200 text-blue-800' : 'bg-green-200 text-green-800'}`}>{email.status}</span>
              </td>
              <td className="p-2">
                {email.attachments && email.attachments.map((att) => (
                  <span
                    key={att.id}
                    className="inline-block bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs mr-1 mb-1 cursor-pointer hover:bg-blue-100 hover:underline"
                    onClick={() => navigate(`/documents?docId=${att.id}`)}
                    onMouseEnter={(e) => handleAttachmentHover(e, att)}
                    onMouseLeave={clearAttachmentHover}
                  >
                    {att.filename}
                  </span>
                ))}
              </td>
              <td className="p-2 flex gap-2">
                <button onClick={() => setModalEmail(email)} className="bg-blue-500 text-white px-2 py-1 rounded text-xs hover:bg-blue-600">View Email</button>
                {/* Add other actions if needed */}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {modalEmail && <EmailModal open={!!modalEmail} onClose={() => setModalEmail(null)} email={modalEmail} />}

      {hoveredAttachmentPreview && (
        <div
          style={{ top: hoveredAttachmentPreview.y + 15, left: hoveredAttachmentPreview.x + 15 }}
          className="fixed z-50 bg-white border rounded shadow-lg p-3 max-w-xs text-xs"
        >
          <p className="font-bold">{hoveredAttachmentPreview.attachment.filename}</p>
          <p className="text-gray-600">{hoveredAttachmentPreview.attachment.content_type}</p>
          {hoveredAttachmentPreview.attachment.content_type.startsWith('image/') && hoveredAttachmentPreview.attachment.thumbnail_base64 ? (
            <img src={`data:${hoveredAttachmentPreview.attachment.content_type};base64,${hoveredAttachmentPreview.attachment.thumbnail_base64}`} alt="Preview" className="max-w-full h-auto mt-2" />
          ) : (
            <p className="mt-1 italic">No visual preview available.</p>
          )}
        </div>
      )}
    </div>
  );
};

export default Inbox;
