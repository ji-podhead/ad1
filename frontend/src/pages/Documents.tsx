// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Unified Document interface based on observed data from /api/documents
interface Document {
  id: number;
  filename: string;
  content_type: string;
  data_b64: string; // Base64 encoded content for preview
  created_at: string;
  is_processed: boolean;
  email_id?: number; // Include if available and needed, though not used in current preview
}

const Documents: React.FC = () => {
  const [allDocs, setAllDocs] = useState<Document[]>([]); // Use unified Document interface
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null); // Use unified Document interface
  const [loadingList, setLoadingList] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const location = useLocation();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null); // Keep for potential future use

  // Fetch list of all documents
  useEffect(() => {
    const fetchAllDocuments = async () => {
      setLoadingList(true);
      setError(null);
      try {
        const response = await fetch('/api/documents'); // Endpoint for all documents
        if (!response.ok) {
          throw new Error(`Failed to fetch document list: ${response.statusText}`);
        }
        const data: Document[] = await response.json(); // Use unified Document interface
        setAllDocs(data);
        console.log("Fetched document list:", data);
      } catch (err) {
        if (err instanceof Error) setError(err.message);
        else setError('An unknown error occurred while fetching document list');
        console.error("Error fetching document list:", err);
      } finally {
        setLoadingList(false);
      }
    };
    fetchAllDocuments();
  }, []);

  // Set selectedDoc based on docId in URL when allDocs is available
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const docIdParam = params.get('docId');

    if (docIdParam) {
      if (allDocs.length > 0) {
        setLoadingDetail(true); // Indicate we are processing selection
        const numericDocId = parseInt(docIdParam, 10);
        const foundDoc = allDocs.find(doc => doc.id === numericDocId);

        if (foundDoc) {
          setSelectedDoc(foundDoc);
          setError(null); // Clear previous errors if doc is found
        } else {
          setSelectedDoc(null); // Clear selection if not found
          setError(`Document with ID ${docIdParam} not found in the loaded list.`);
          console.error(`Document with ID ${docIdParam} not found in allDocs.`);
        }
        setLoadingDetail(false);
      } else {
        // allDocs is not yet populated. We should wait for it.
        // Set loadingDetail to true to indicate that we are waiting for data to find the selected document.
        setLoadingDetail(true);
        setSelectedDoc(null); // Ensure no stale selectedDoc is shown
        // setError("Document list is loading, attempting to select document shortly..."); // Optional: inform user
      }
    } else {
      // No docId in URL, so clear any selection and loading states for detail view
      setSelectedDoc(null);
      setLoadingDetail(false);
      setError(null); // Clear any previous errors
    }
  }, [location.search, allDocs]); // Re-run when docIdParam changes or allDocs populates

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const filteredDocs = allDocs.filter(doc =>
    doc.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
    doc.content_type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatDate = (dateString: string | null | undefined): string => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString();
    } catch (e) {
      return dateString; 
    }
  };

  const renderPreview = (doc: Document | null) => { // Parameter type updated to Document
    if (loadingDetail) {
        return <div className="p-4 text-gray-500">Loading document details...</div>;
    }
    if (!doc) { // Handles both null and cases where data_b64 might be missing if interface allowed it
      return <div className="p-4 text-gray-500">Select a document to view its preview or document not found.</div>;
    }
    if (!doc.data_b64) {
        return <div className="p-4 text-gray-500">Preview data is not available for this document.</div>;
    }


    const { content_type, data_b64, filename } = doc;

    if (content_type.startsWith('image/')) {
      return <img src={`data:${content_type};base64,${data_b64}`} alt={filename} className="max-w-full max-h-full object-contain" />;
    } else if (content_type === 'application/pdf') {
      try {
        const byteCharacters = atob(data_b64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'application/pdf' });
        const pdfUrl = URL.createObjectURL(blob);
        return <iframe src={pdfUrl} title={filename} className="w-full h-full border-none" />;
      } catch (e) {
        console.error("Error creating PDF blob URL:", e);
        return <div className="p-4 text-red-500">Error loading PDF preview.</div>;
      }
    } else if (content_type.startsWith('text/') || content_type === 'application/json') {
      try {
        const textContent = atob(data_b64);
        return <pre className="w-full h-full p-2 bg-gray-50 rounded overflow-auto text-sm whitespace-pre-wrap break-all">{textContent}</pre>;
      } catch (e) {
        console.error("Error decoding text content:", e);
        return <div className="p-4 text-red-500">Error loading text preview.</div>;
      }
    } else {
      return <div className="p-4 text-gray-500">Preview not available for {content_type}.</div>;
    }
  };

  return (
    <div className="flex h-[calc(100vh-theme_header_height)]"> {/* Adjust theme_header_height based on your layout */}
      {/* Left Panel: Document List */}
      <div className="w-1/3 border-r overflow-y-auto p-4">
        <h1 className="text-xl font-bold mb-4">Documents</h1>
        <input
          type="text"
          placeholder="Search documents..."
          value={searchTerm}
          onChange={handleSearchChange}
          className="w-full p-2 border rounded mb-4"
        />
        {loadingList && <p>Loading document list...</p>}
        {error && !loadingList && <p className="text-red-500">{error}</p>}
        {!loadingList && filteredDocs.length === 0 && !error && <p>No documents found.</p>}
        <ul className="space-y-2">
          {filteredDocs.map(doc => (
            <li key={doc.id}
                className={`p-2 rounded cursor-pointer hover:bg-gray-100 ${selectedDoc?.id === doc.id ? 'bg-blue-100 border-blue-500' : 'border'}`}
                onClick={() => navigate(`/documents?docId=${doc.id}`)}>
              <div className="font-semibold">{doc.filename}</div>
              <div className="text-xs text-gray-500">{doc.content_type} - {formatDate(doc.created_at)}</div>
            </li>
          ))}
        </ul>
      </div>

      {/* Right Panel: Document Preview */}
      <div className="w-2/3 p-4 flex flex-col bg-gray-50">
        {selectedDoc && !loadingDetail && ( // Ensure not loading before showing details
            <div className="mb-2 pb-2 border-b">
                <h2 className="text-lg font-semibold">{selectedDoc.filename}</h2>
                <p className="text-sm text-gray-600">{selectedDoc.content_type} - Created: {formatDate(selectedDoc.created_at)}</p>
            </div>
        )}
        <div className="flex-grow border rounded bg-white overflow-auto">
          {renderPreview(selectedDoc)}
        </div>
        {selectedDoc && !loadingDetail && ( // Ensure not loading before showing button
            <div className="mt-4 pt-4 border-t flex justify-end">
                <button
                    onClick={() => navigate(`/validation?docId=${selectedDoc.id}`)}
                    className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
                    Proceed to Validation
                </button>
            </div>
        )}
      </div>
    </div>
  );
};

export default Documents;
