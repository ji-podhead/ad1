// DocumentModal.tsx
import React from 'react';

interface DocumentModalProps {
  open: boolean;
  onClose: () => void;
  doc: any;
}

const DocumentModal: React.FC<DocumentModalProps> = ({ open, onClose, doc }) => {
  if (!open || !doc) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 relative animate-fade-in-up">
        <button onClick={onClose} className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-2xl">×</button>
        <h2 className="text-xl font-bold mb-2">{doc.name}</h2>
        <div className="mb-2 text-sm text-gray-500">Uploaded: {doc.uploaded}</div>
        <div className="mb-2 text-sm text-gray-500">Status: {doc.status}</div>
        <div className="mb-4 text-gray-700 whitespace-pre-line">This is a demo preview for {doc.name}.\nLorem ipsum dolor sit amet, consectetur adipiscing elit.\nSed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</div>
        <div className="flex gap-2">
          <button className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700" onClick={onClose}>Validate</button>
        </div>
      </div>
    </div>
  );
};

export default DocumentModal;
