// EmailModal.tsx
import React from 'react';

interface EmailModalProps {
  open: boolean;
  onClose: () => void;
  email: any;
}

const EmailModal: React.FC<EmailModalProps> = ({ open, onClose, email }) => {
  if (!open || !email) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 relative animate-fade-in-up">
        <button onClick={onClose} className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-2xl">×</button>
        <h2 className="text-xl font-bold mb-2">{email.subject}</h2>
        <div className="mb-2 text-sm text-gray-500">From: {email.from || email.sender} | {email.date}</div>
        <div className="mb-4 text-gray-700 whitespace-pre-line">{email.body || 'This is a demo email body for: ' + email.subject + '\nLorem ipsum dolor sit amet, consectetur adipiscing elit.\nSed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'}</div>

        {email.attachments && email.attachments.length > 0 && (
          <div className="mb-4">
            <h3 className="text-md font-semibold mb-2">Attachments:</h3>
            <ul className="list-disc pl-5">
              {email.attachments.map((attachment: any) => (
                <li key={attachment.id} className="mb-1">
                  <a
                    href={`/api/emails/${email.id}/attachments/${attachment.id}`}
                    className="text-blue-600 hover:text-blue-800 hover:underline"
                    target="_blank" // Opens in new tab, browser handles download
                    rel="noopener noreferrer"
                    download // Suggests to browser to download, works best if backend sends Content-Disposition
                  >
                    {attachment.filename}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex gap-2">
          {/* Assuming email.id is the internal_email_id for the validation link */}
          <a href={`/validation?emailId=${email.id}`} className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700" onClick={onClose}>Zur Validierung</a>
        </div>
      </div>
    </div>
  );
};

export default EmailModal;

// Note: For the attachments to work, the 'email' object structure should be:
// interface Email {
//   id: number; // This is internal_email_id for the API call
//   subject: string;
//   from?: string; // or sender
//   sender?: string;
//   date: string;
//   body: string;
//   attachments?: Array<{
//     id: number; // This is document_db_id for the API call
//     filename: string;
//     // other fields like content_type, size if available and needed for display
//   }>;
// }
// The backend API endpoint GET /api/emails/{email_id} must provide this structure.
