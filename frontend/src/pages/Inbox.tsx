// Inbox page: List, filter, and label emails. Trigger workflows on incoming emails. See processing status.
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

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
  date: string; // Keep as string for display, backend now provides received_at
  received_at: string; // Added received_at from backend
  attachments: Attachment[];
  body: string;
}

const Inbox: React.FC = () => {
  const [filter, setFilter] = useState('All');
  const [hoveredEmailId, setHoveredEmailId] = useState<number | null>(null);
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const [hoveredAttachmentPreview, setHoveredAttachmentPreview] = useState<{
    x: number;
    y: number;
    attachment: Attachment;
  } | null>(null);

  // New state for selected email and active tab
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [activeEmailToolTab, setActiveEmailToolTab] = useState<'details' | 'attachments' | 'reply'>('details');

  useEffect(() => {
    const fetchEmails = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/emails');
        if (!response.ok) throw new Error('Failed to fetch emails');
        const apiData = await response.json();
        console.log("Fetched emails:", apiData);
        // Map backend data to frontend Email interface
        setEmails(apiData.map((item: any) => ({
          id: item.id,
          subject: item.subject,
          from: item.sender,
          status: item.status || 'Pending',
          date: item.received_at ? new Date(item.received_at).toLocaleDateString() : 'N/A', // Format date for display
          received_at: item.received_at, // Store original received_at
          attachments: item.attachments || [],
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

  const handleAttachmentHover = (e: React.MouseEvent, attachment: Attachment) => {
    setHoveredAttachmentPreview({ x: e.clientX, y: e.clientY, attachment });
  };

  const clearAttachmentHover = () => {
    setHoveredAttachmentPreview(null);
  };

  const handleEmailRowClick = (email: Email) => {
    setSelectedEmail(email);
    setActiveEmailToolTab('details'); // Default to details tab on email selection
  };

  const filtered = filter === 'All' ? emails : emails.filter(e => e.status === filter);

  if (loading && emails.length === 0) return <div className="p-6 text-center">Loading emails...</div>;
  if (error) return <div className="p-6 text-center text-red-500">Error: {error}</div>;
  if (!loading && emails.length === 0) return <div className="p-6 text-center">No emails found.</div>;

  return (
    <div className="p-6 flex flex-col h-screen"> {/* Use flex-col and h-screen for layout */}
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
      
      {/* Email List Table */}
      <div className="flex-grow overflow-y-auto mb-4"> {/* Make table scrollable */}
        <table className="w-full border bg-white rounded shadow">
          <thead>
            <tr className="bg-gray-100">
              <th className="p-2 text-left">Subject</th>
              <th className="p-2 text-left">From</th>
              <th className="p-2 text-left">Date</th>
              <th className="p-2 text-left">Status</th>
              <th className="p-2 text-left">Attachments</th>
              {/* Removed Actions column */}
            </tr>
          </thead>
          <tbody>
            {filtered.map(email => (
              <tr
                key={email.id}
                className={`border-t group relative cursor-pointer ${selectedEmail?.id === email.id ? 'bg-blue-50' : ''}`}
                onMouseEnter={() => setHoveredEmailId(email.id)}
                onMouseLeave={() => setHoveredEmailId(null)}
                onClick={() => handleEmailRowClick(email)} // Use new handler
              >
                <td className="p-2 text-blue-700 hover:underline relative">
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
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent row click when clicking attachment
                        navigate(`/documents?docId=${att.id}`);
                      }}
                      onMouseEnter={(e) => handleAttachmentHover(e, att)}
                      onMouseLeave={clearAttachmentHover}
                    >
                      {att.filename}
                    </span>
                  ))}
                </td>
                {/* Removed Actions cell */}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Email Tools Window */}
      {selectedEmail && (
        <div className="border-t pt-4 mt-4">
          <h2 className="text-xl font-bold mb-2">Email Details</h2>
          <div className="flex border-b mb-4">
            <button
              className={`py-2 px-4 font-medium text-sm ${activeEmailToolTab === 'details' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setActiveEmailToolTab('details')}
            >
              Details
            </button>
            <button
              className={`py-2 px-4 font-medium text-sm ${activeEmailToolTab === 'attachments' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setActiveEmailToolTab('attachments')}
            >
              Attachments ({selectedEmail.attachments.length})
            </button>
            <button
              className={`py-2 px-4 font-medium text-sm ${activeEmailToolTab === 'reply' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
              onClick={() => setActiveEmailToolTab('reply')}
            >
              Reply
            </button>
          </div>

          {/* Tab Content */}
          <div className="bg-white p-4 rounded shadow-inner overflow-y-auto max-h-60"> {/* Added max-h and overflow */}
            {activeEmailToolTab === 'details' && (
              <div>
                <p><strong>Subject:</strong> {selectedEmail.subject}</p>
                <p><strong>From:</strong> {selectedEmail.from}</p>
                <p><strong>Date:</strong> {selectedEmail.date}</p>
                <p><strong>Status:</strong> {selectedEmail.status}</p>
                <h3 className="font-semibold mt-4 mb-2">Body:</h3>
                <div className="whitespace-pre-wrap text-sm">{selectedEmail.body}</div> {/* Preserve whitespace */}
              </div>
            )}
            {activeEmailToolTab === 'attachments' && (
              <div>
                <h3 className="font-semibold mb-2">Attachments:</h3>
                {selectedEmail.attachments.length > 0 ? (
                  <ul className="list-disc pl-5 text-sm">
                    {selectedEmail.attachments.map(att => (
                      <li key={att.id} className="mb-1">
                         <span
                            className="inline-block bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs mr-1 mb-1 cursor-pointer hover:bg-blue-100 hover:underline"
                            onClick={(e) => {
                              e.stopPropagation(); // Prevent any parent click handlers
                              navigate(`/documents?docId=${att.id}`);
                            }}
                             onMouseEnter={(e) => handleAttachmentHover(e, att)}
                             onMouseLeave={clearAttachmentHover}
                          >
                            {att.filename} ({att.content_type})
                          </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">No attachments for this email.</p>
                )}
              </div>
            )}
            {activeEmailToolTab === 'reply' && (
              <div>
                <h3 className="font-semibold mb-2">Reply to {selectedEmail.from}</h3>
                {/* Simple Reply Form - Sending functionality needs a backend endpoint */}
                <div className="space-y-2">
                  <div>
                    <label htmlFor="reply-subject" className="block text-sm font-medium text-gray-700">Subject:</label>
                    <input
                      type="text"
                      id="reply-subject"
                      value={`Re: ${selectedEmail.subject}`}
                      readOnly // Subject is typically pre-filled for replies
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm bg-gray-100"
                    />
                  </div>
                  <div>
                    <label htmlFor="reply-body" className="block text-sm font-medium text-gray-700">Body:</label>
                    <textarea
                      id="reply-body"
                      rows={5}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                      placeholder={`\n\n---\nOriginal Message:\nFrom: ${selectedEmail.from}\nDate: ${selectedEmail.date}\nSubject: ${selectedEmail.subject}\n\n${selectedEmail.body}`}
                    ></textarea>
                  </div>
                  <div>
                    {/* Sending functionality needs a backend API endpoint */}
                    <button
                      onClick={() => alert("Reply functionality is not yet implemented.")}
                      className="inline-flex justify-center rounded-md border border-transparent bg-blue-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                      Send Reply
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Attachment Hover Preview (keep existing logic) */}
      {hoveredAttachmentPreview && (
        <div
          style={{ top: hoveredAttachmentPreview.y + 15, left: hoveredAttachmentPreview.x + 15 }}
          className="fixed z-50 bg-white border rounded shadow-lg p-3 max-w-xs text-xs"
        >
          <p className="font-bold">{hoveredAttachmentPreview.attachment.filename}</p>
          <p className="text-gray-600">{hoveredAttachmentPreview.attachment.content_type}</p>
          {/* Note: thumbnail_base64 is not currently fetched for list view, so this part might not show previews */}
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
