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
        <div className="mb-2 text-sm text-gray-500">From: {email.from} | {email.date}</div>
        <div className="mb-4 text-gray-700 whitespace-pre-line">{email.body || 'This is a demo email body for: ' + email.subject + '\nLorem ipsum dolor sit amet, consectetur adipiscing elit.\nSed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'}</div>
        <div className="flex gap-2">
          <a href="/validation?emailId=" className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700" onClick={onClose}>Zur Validierung</a>
        </div>
      </div>
    </div>
  );
};

export default EmailModal;
