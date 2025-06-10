// EmailModal.tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface Attachment {
  id: number;
  filename: string;
  content_type: string;
  thumbnail_base64?: string;
}

interface EmailModalProps {
  open: boolean;
  onClose: () => void;
  email: {
    id: number;
    subject: string;
    from: string;
    date: string; // Expecting formatted date string
    body: string;
    attachments: Attachment[];
  } | null; // Allow email to be null
}

const EmailModal: React.FC<EmailModalProps> = ({ open, onClose, email }) => {
  const navigate = useNavigate(); // Initialize navigate
  const [hoveredAttachmentPreview, setHoveredAttachmentPreview] = useState<{
    x: number;
    y: number;
    attachment: Attachment;
  } | null>(null);

  if (!open || !email) return null;

  const handleAttachmentHover = (e: React.MouseEvent, attachment: Attachment) => {
    setHoveredAttachmentPreview({ x: e.clientX, y: e.clientY, attachment });
  };

  const clearAttachmentHover = () => {
    setHoveredAttachmentPreview(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 relative animate-fade-in-up max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-3 right-3 text-gray-400 hover:text-gray-700 text-2xl">&times;</button>
        <h2 className="text-xl font-bold mb-1">{email.subject}</h2>
        <div className="mb-2 text-sm text-gray-500">From: {email.from}</div>
        <div className="mb-4 text-sm text-gray-500">Date: {email.date}</div>
        
        <div className="mb-4">
          <h3 className="text-md font-semibold mb-1">Attachments:</h3>
          {email.attachments && email.attachments.length > 0 ? (
            <ul className="list-none p-0 m-0">
              {email.attachments.map((att) => (
                <li key={att.id} 
                    className="inline-block bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs mr-1 mb-1 cursor-pointer hover:bg-blue-100 hover:underline"
                    onClick={() => {
                        navigate(`/documents?docId=${att.id}`);
                        onClose(); // Close modal on navigation
                    }}
                    onMouseEnter={(e) => handleAttachmentHover(e, att)}
                    onMouseLeave={clearAttachmentHover}
                >
                  {att.filename}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No attachments.</p>
          )}
        </div>

        <div className="mb-4 text-gray-700 whitespace-pre-line border-t pt-4">
          {email.body || 'No body content available.'}
        </div>
        
        <div className="flex gap-2 mt-4 border-t pt-4">
          <button 
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
            onClick={() => {
              navigate(`/validation?emailId=${email.id}`);
              onClose(); // Close modal on navigation
            }}
          >
            Zur Validierung
          </button>
          <button 
            className="bg-gray-300 text-gray-800 px-4 py-2 rounded hover:bg-gray-400"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>

      {hoveredAttachmentPreview && (
        <div
          style={{ top: hoveredAttachmentPreview.y + 15, left: hoveredAttachmentPreview.x + 15 }}
          className="fixed z-[60] bg-white border rounded shadow-lg p-3 max-w-xs text-xs"
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

export default EmailModal;
