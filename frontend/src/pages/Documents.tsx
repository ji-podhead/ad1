// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useRef, useState, useEffect } from 'react';
import DocumentModal from '../components/DocumentModal';
import { useLocation } from 'react-router-dom';

interface Document {
  id: number;
  subject: string;
  sender: string;
  body: string; // Or a summary
  received_at: string;
  type: string | null;
  short_description: string | null;
  label: string | null; // Added to match backend Email model
}

const Documents: React.FC = () => {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [hovered, setHovered] = useState<number | null>(null);
  const [modalDoc, setModalDoc] = useState<Document | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const location = useLocation();

  const fetchDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/emails'); // Assuming /api/emails is the endpoint for documents/emails
      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.statusText}`);
      }
      const data: Document[] = await response.json();
      setDocs(data);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unknown error occurred');
      }
      console.error("Error fetching documents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const docSubject = params.get('doc'); // Assuming 'doc' param refers to subject
    if (docSubject) {
      setSearch(docSubject);
    }
  }, [location.search]);

  const handleUpload = () => {
    // This function needs to be re-evaluated.
    // For now, it's disabled as it doesn't align with fetching from backend
    // and the 'emails' table structure.
    alert('Upload functionality is temporarily disabled and needs backend integration.');
    if (fileInput.current) {
      fileInput.current.value = ""; // Reset file input
    }
    // if (fileInput.current?.files?.length) {
    //   const file = fileInput.current.files[0];
    //   // This is demo logic, replace with actual upload and backend update
    //   const newDoc: Document = {
    //     id: Date.now(),
    //     subject: file.name,
    //     sender: 'Local Upload',
    //     body: 'File content placeholder',
    //     received_at: new Date().toISOString(),
    //     type: 'Uploaded', // Example type
    //   };
    //   setDocs(prevDocs => [newDoc, ...prevDocs]);
    // }
  };

  const filteredDocs = docs.filter(doc =>
    doc.subject.toLowerCase().includes(search.toLowerCase()) ||
    doc.sender.toLowerCase().includes(search.toLowerCase()) ||
    (doc.type && doc.type.toLowerCase().includes(search.toLowerCase()))
  );

  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (e) {
      return dateString; // Return original if formatting fails
    }
  };


  if (loading) {
    return <div className="p-6 text-center">Loading documents...</div>;
  }

  if (error) {
    return <div className="p-6 text-center text-red-500">Error loading documents: {error}</div>;
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Documents (Emails)</h1>
      <div className="mb-4 flex gap-2 items-center">
        <input type="file" ref={fileInput} className="border rounded px-2 py-1" disabled /> {/* Disabled for now */}
        <button onClick={handleUpload} className="bg-blue-600 text-white px-4 py-2 rounded opacity-50 cursor-not-allowed" disabled>Upload</button> {/* Disabled for now */}
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by subject, sender, type..."
          className="border rounded px-2 py-1 ml-4 flex-1"
        />
      </div>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Subject</th>
            <th className="p-2 text-left">Sender</th>
            <th className="p-2 text-left">Received At</th>
            <th className="p-2 text-left">Type</th>
            <th className="p-2 text-left">Short Description</th>
            {/* <th className="p-2 text-left">Status</th> */} {/* Status field removed for now, can be derived or added if needed */}
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
                {doc.subject}
                {hovered === doc.id && (
                  <div className="absolute left-0 top-full mt-1 z-30 bg-white border rounded shadow-lg p-3 w-auto min-w-[300px] max-w-md text-xs animate-fade-in-up">
                    <div className="font-bold mb-1">{doc.subject}</div>
                    <div className="mb-1 text-gray-600">From: {doc.sender}</div>
                    <div className="mb-1 text-gray-500">Received: {formatDate(doc.received_at)}</div>
                    <div className="mb-1 text-gray-400">Type: {doc.type || 'N/A'}</div>
                    <div className="mb-1 text-gray-400">Summary: {doc.short_description || 'N/A'}</div>
                    <div className="text-gray-700 whitespace-pre-line mt-2">
                      Body Preview: {doc.body ? (doc.body.substring(0, 150) + (doc.body.length > 150 ? '...' : '')) : 'No body preview.'}
                    </div>
                  </div>
                )}
              </td>
              <td className="p-2">{doc.sender}</td>
              <td className="p-2">{formatDate(doc.received_at)}</td>
              <td className="p-2">{doc.type || 'N/A'}</td>
              <td className="p-2 truncate max-w-xs" title={doc.short_description || undefined}>{doc.short_description || 'N/A'}</td>
              {/* <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${doc.status === 'Processing' ? 'bg-blue-200' : doc.status === 'Needs Validation' ? 'bg-yellow-200' : 'bg-green-200'}`}>{doc.status}</span>
              </td> */}
              <td className="p-2 flex gap-2">
                {/* Simplified actions for now */}
                <button className="bg-blue-500 text-white px-2 py-1 rounded text-xs" onClick={() => setModalDoc(doc)}>View</button>
                {/* <button className="bg-green-500 text-white px-2 py-1 rounded text-xs" onClick={() => setModalDoc(doc)}>Validate</button> */}
                <button className="bg-gray-300 text-gray-800 px-2 py-1 rounded text-xs">Delete (NYI)</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {modalDoc && (
        <DocumentModal
          open={!!modalDoc}
          onClose={() => setModalDoc(null)}
          doc={{ // Adapt DocumentModal props if necessary.
            name: modalDoc.subject,
            status: modalDoc.type || 'N/A',
            uploaded: formatDate(modalDoc.received_at),
            body: modalDoc.body,
            // Potentially pass short_description to DocumentModal if it's designed to show it
            short_description: modalDoc.short_description,
            // Pass other fields as needed by DocumentModal, e.g. sender, type explicitly
            sender: modalDoc.sender,
            type: modalDoc.type,
          }}
        />
      )}
    </div>
  );
};

export default Documents;
