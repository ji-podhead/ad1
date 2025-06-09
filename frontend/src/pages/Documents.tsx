// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useRef, useState, useEffect } from 'react';
import DocumentModal from '../components/DocumentModal';
import { useLocation } from 'react-router-dom';

interface Document {
  id: number;
  email_id: number; // Link to the email
  filename: string;
  content_type: string;
  is_processed: boolean;
  created_at: string; // Use string for date/time from backend
  // Removed email-specific fields: subject, sender, body, received_at, type, short_description, label
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
      const response = await fetch('/api/documents'); // Change endpoint to fetch documents
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

  const handleDeleteDocument = async (docId: number) => {
    if (window.confirm(`Are you sure you want to delete document with ID ${docId}?`)) {
      try {
        const response = await fetch(`/api/documents/${docId}`, {
          method: 'DELETE',
        });

        if (!response.ok) {
          throw new Error(`Failed to delete document: ${response.statusText}`);
        }

        // Remove the deleted document from the state
        setDocs(prevDocs => prevDocs.filter(doc => doc.id !== docId));
        alert(`Document with ID ${docId} deleted successfully.`);

      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('An unknown error occurred during deletion');
        }
        console.error("Error deleting document:", err);
        alert(`Failed to delete document with ID ${docId}.`);
      }
    }
  };

  const filteredDocs = docs.filter(doc =>
    doc.filename.toLowerCase().includes(search.toLowerCase()) ||
    doc.content_type.toLowerCase().includes(search.toLowerCase())
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
          placeholder="Search by filename, content type..."
          className="border rounded px-2 py-1 ml-4 flex-1"
        />
      </div>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Filename</th>
            <th className="p-2 text-left">Content Type</th>
            <th className="p-2 text-left">Created At</th>
            <th className="p-2 text-left">Processed</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredDocs.map(doc => (
            <tr key={doc.id} className="border-t group relative">
              <td
                className="p-2 cursor-pointer text-blue-700 hover:underline relative"
                // Remove hover preview for now, will implement document preview separately
                // onMouseEnter={() => setHovered(doc.id)}
                // onMouseLeave={() => setHovered(null)}
                // onClick={() => setModalDoc(doc)}
              >
                {doc.filename}
                {/* Remove email hover preview content */}
                {/* {hovered === doc.id && (...) } */}
              </td>
              <td className="p-2">{doc.content_type}</td>
              <td className="p-2">{formatDate(doc.created_at)}</td>
              <td className="p-2">{doc.is_processed ? 'Yes' : 'No'}</td>
              <td className="p-2 flex gap-2">
                {/* Update View button to potentially open document preview modal */}
                <button className="bg-blue-500 text-white px-2 py-1 rounded text-xs" onClick={() => setModalDoc(doc)}>View</button>
                {/* Update Delete button to use the correct endpoint */}
                <button
                  className="bg-red-500 text-white px-2 py-1 rounded text-xs hover:bg-red-600"
                  onClick={() => handleDeleteDocument(doc.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {/* Update DocumentModal usage to pass document data */}
      {modalDoc && (
        <DocumentModal
          open={!!modalDoc}
          onClose={() => setModalDoc(null)}
          doc={modalDoc} // Pass the full document object
        />
      )}
    </div>
  );
};

export default Documents;
