// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useRef, useState } from 'react';

const demoDocs = [
  { id: 1, name: 'Registration_Form.pdf', status: 'Processing', uploaded: '2025-06-03' },
  { id: 2, name: 'Case_Notes.docx', status: 'Needs Validation', uploaded: '2025-06-02' },
  { id: 3, name: 'Final_Report.pdf', status: 'Validated', uploaded: '2025-06-01' },
];

const Documents: React.FC = () => {
  const [docs, setDocs] = useState(demoDocs);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleUpload = () => {
    if (fileInput.current?.files?.length) {
      const file = fileInput.current.files[0];
      setDocs([{ id: Date.now(), name: file.name, status: 'Processing', uploaded: new Date().toISOString().slice(0,10) }, ...docs]);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Documents</h1>
      <div className="mb-4 flex gap-2 items-center">
        <input type="file" ref={fileInput} className="border rounded px-2 py-1" />
        <button onClick={handleUpload} className="bg-blue-600 text-white px-4 py-2 rounded">Upload</button>
      </div>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Name</th>
            <th className="p-2 text-left">Uploaded</th>
            <th className="p-2 text-left">Status</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {docs.map(doc => (
            <tr key={doc.id} className="border-t">
              <td className="p-2">{doc.name}</td>
              <td className="p-2">{doc.uploaded}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${doc.status === 'Processing' ? 'bg-blue-200' : doc.status === 'Needs Validation' ? 'bg-yellow-200' : 'bg-green-200'}`}>{doc.status}</span>
              </td>
              <td className="p-2 flex gap-2">
                <button className="bg-green-500 text-white px-2 py-1 rounded text-xs">Validate</button>
                <button className="bg-gray-300 text-gray-800 px-2 py-1 rounded text-xs">Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Documents;
