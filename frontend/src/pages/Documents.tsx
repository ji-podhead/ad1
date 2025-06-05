// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useRef, useState } from 'react';
import DocumentModal from '../components/DocumentModal';
import { useLocation } from 'react-router-dom';

const demoDocs = [
  { id: 1, name: 'Registration_Form.pdf', status: 'Processing', uploaded: '2025-06-03' },
  { id: 2, name: 'Case_Notes.docx', status: 'Needs Validation', uploaded: '2025-06-02' },
  { id: 3, name: 'Final_Report.pdf', status: 'Validated', uploaded: '2025-06-01' },
];

const Documents: React.FC = () => {
  const [docs, setDocs] = useState(demoDocs);
  const [search, setSearch] = useState('');
  const [hovered, setHovered] = useState<number|null>(null);
  const [modalDoc, setModalDoc] = useState<any|null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const location = useLocation();

  // Open search if doc param is present
  React.useEffect(() => {
    const params = new URLSearchParams(location.search);
    const docName = params.get('doc');
    if (docName) {
      setSearch(docName);
    }
  }, [location.search]);

  const handleUpload = () => {
    if (fileInput.current?.files?.length) {
      const file = fileInput.current.files[0];
      setDocs([{ id: Date.now(), name: file.name, status: 'Processing', uploaded: new Date().toISOString().slice(0,10) }, ...docs]);
    }
  };

  const filteredDocs = docs.filter(doc => doc.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Documents</h1>
      <div className="mb-4 flex gap-2 items-center">
        <input type="file" ref={fileInput} className="border rounded px-2 py-1" />
        <button onClick={handleUpload} className="bg-blue-600 text-white px-4 py-2 rounded">Upload</button>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search documents..."
          className="border rounded px-2 py-1 ml-4 flex-1"
        />
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
          {filteredDocs.map(doc => (
            <tr key={doc.id} className="border-t group relative">
              <td
                className="p-2 cursor-pointer text-blue-700 hover:underline relative"
                onMouseEnter={() => setHovered(doc.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setModalDoc(doc)}
              >
                {doc.name}
                {hovered === doc.id && (
                  <div className="absolute left-0 top-full mt-1 z-30 bg-white border rounded shadow-lg p-3 w-72 text-xs animate-fade-in-up">
                    <div className="font-bold mb-1">{doc.name}</div>
                    <div className="mb-1 text-gray-500">Uploaded: {doc.uploaded}</div>
                    <div className="mb-1 text-gray-400">Status: {doc.status}</div>
                    <div className="text-gray-700 whitespace-pre-line">This is a demo preview for {doc.name}.\nLorem ipsum dolor sit amet, consectetur adipiscing elit.</div>
                  </div>
                )}
              </td>
              <td className="p-2">{doc.uploaded}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${doc.status === 'Processing' ? 'bg-blue-200' : doc.status === 'Needs Validation' ? 'bg-yellow-200' : 'bg-green-200'}`}>{doc.status}</span>
              </td>
              <td className="p-2 flex gap-2">
                <button className="bg-green-500 text-white px-2 py-1 rounded text-xs" onClick={() => setModalDoc(doc)}>Validate</button>
                <button className="bg-gray-300 text-gray-800 px-2 py-1 rounded text-xs">Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <DocumentModal open={!!modalDoc} onClose={() => setModalDoc(null)} doc={modalDoc} />
    </div>
  );
};

export default Documents;
