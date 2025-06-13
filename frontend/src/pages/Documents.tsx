// Documents page: Upload, view, and manage documents. See processing status and link to validation.
import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

// Unified Document interface based on observed data from /api/documents
interface Document {
  id: number;
  filename: string;
  content_type: string;
  data_b64: string | null; 
  created_at: string;
  is_processed: boolean;
  email_id?: number; 
  processed_data?: string | null; // Updated type to string
}

// Interface for the email summary details (to be fetched)
interface EmailSummary {
  id: number;
  subject: string;
  type: string | null; // Assuming type is email classification topic
  short_description: string | null;
  received_at: string; // Or use created_at from email record
}

// Interface for document-specific audit events (to be fetched)
interface DocumentAuditEvent {
  id: number;
  event_type: string;
  username: string;
  timestamp: string;
  data: Record<string, any> | null;
}

const Documents: React.FC = () => {
  const [allDocs, setAllDocs] = useState<Document[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [loadingList, setLoadingList] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false); 
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const location = useLocation();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<'info' | 'results' | 'events'>('info');
  const [currentPageNumber, setCurrentPageNumber] = useState<number>(1); // For processed_data pagination
  
  // States for tab content
  const [emailSummary, setEmailSummary] = useState<EmailSummary | null>(null);
  const [loadingEmailSummary, setLoadingEmailSummary] = useState<boolean>(false);
  const [editedProcessedText, setEditedProcessedText] = useState<string>("");
  const [documentEvents, setDocumentEvents] = useState<DocumentAuditEvent[]>([]);
  const [loadingDocumentEvents, setLoadingDocumentEvents] = useState<boolean>(false);

  // New state for parsed processed data
  const [parsedProcessedData, setParsedProcessedData] = useState<{ filename: string; results: Array<{ page_number: number; extracted_text: string; error?: string }> } | null>(null);

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
      const numericDocId = parseInt(docIdParam, 10);
      if (allDocs.length > 0) {
        setLoadingDetail(true); 
        const foundDoc = allDocs.find(doc => doc.id === numericDocId);

        if (foundDoc) {
          if (selectedDoc?.id !== foundDoc.id) {
            setSelectedDoc(foundDoc);
            // Initialize editedProcessedText with the first page's text or empty if no processed_data
            let firstPageText = "";
            let parsedData = null;
            // Check if processed_data is a non-empty string before attempting JSON.parse
            if (foundDoc.processed_data && typeof foundDoc.processed_data === 'string' && foundDoc.processed_data.trim() !== '' && foundDoc.processed_data.trim().toLowerCase() !== 'null') {
              try {
                parsedData = JSON.parse(foundDoc.processed_data);
                // Verify the parsed data has the expected structure
                if (parsedData && typeof parsedData === 'object' && parsedData.results && Array.isArray(parsedData.results)) {
                  setParsedProcessedData(parsedData);
                  if (parsedData.results.length > 0) {
                    firstPageText = parsedData.results[0].extracted_text;
                  }
                } else {
                  console.warn("Processed data is not in expected format (missing 'results' array):", parsedData);
                  setParsedProcessedData(null); // Data is not in expected format
                  setError("Processed data is not in the expected format.");
                }
              } catch (e) {
                console.error("Error parsing processed_data JSON:", e);
                setParsedProcessedData(null); // JSON parsing failed
                setError("Error parsing processed data for this document.");
              }
            } else {
              // processed_data is null, not a string, empty string, or "null"
              setParsedProcessedData(null);
              console.log("No valid processed_data string found for parsing.");
            }
            setEditedProcessedText(firstPageText);
            setCurrentPageNumber(1); // Reset to first page
            setEmailSummary(null);
            setDocumentEvents([]);
            setActiveTab('info'); // Default to info tab on new doc selection
          }
          setError(null);
        } else {
          setSelectedDoc(null);
          setEditedProcessedText("");
          setCurrentPageNumber(1);
          setError(`Document with ID ${docIdParam} not found.`);
          console.error(`Document with ID ${docIdParam} not found in allDocs.`);
        }
        setLoadingDetail(false);
      } else if (loadingList) {
        setLoadingDetail(true);
        setSelectedDoc(null);
        setEditedProcessedText("");
        setCurrentPageNumber(1);
      }
    } else {
      setSelectedDoc(null);
      setEditedProcessedText("");
      setCurrentPageNumber(1);
      setLoadingDetail(false);
      setError(null); 
      setParsedProcessedData(null); // Clear parsed data
    }
  }, [location.search, allDocs, loadingList]);

  // Update editedProcessedText when currentPageNumber or parsedProcessedData changes
  useEffect(() => {
    if (parsedProcessedData?.results && Array.isArray(parsedProcessedData.results) && parsedProcessedData.results.length > 0) {
      const pageData = parsedProcessedData.results.find(p => p.page_number === currentPageNumber);
      setEditedProcessedText(pageData ? pageData.extracted_text : "");
    } else {
        setEditedProcessedText(""); // Clear if no doc selected or processed_data is not available/valid
    }
  }, [parsedProcessedData, currentPageNumber]);

  // Fetch email summary when selectedDoc changes and has an email_id
  useEffect(() => {
    if (selectedDoc && selectedDoc.email_id && activeTab === 'info') {
      const fetchEmailSummary = async () => {
        setLoadingEmailSummary(true);
        try {
          // TODO: Replace with actual API call: /api/emails/{selectedDoc.email_id} or a summary specific endpoint
          // Mocking for now
          const response = await fetch(`/api/emails/${selectedDoc.email_id}`);
          if (!response.ok) throw new Error('Failed to fetch email summary');
          const data: EmailSummary = await response.json();
          setEmailSummary(data);
        } catch (err) {
          console.error("Error fetching email summary:", err);
          setEmailSummary(null);
        } finally {
          setLoadingEmailSummary(false);
        }
      };
      fetchEmailSummary();
    } else if (selectedDoc && !selectedDoc.email_id && activeTab === 'info') {
        setEmailSummary(null); // Clear email summary if document is not linked to an email
    }
  }, [selectedDoc, activeTab]);

  // Fetch document events when selectedDoc changes and events tab is active
  useEffect(() => {
    if (selectedDoc && activeTab === 'events') {
      const fetchDocumentEvents = async () => {
        setLoadingDocumentEvents(true);
        try {
          // TODO: Replace with actual API call: /api/audit/document/{selectedDoc.id}
          // Mocking for now
          // const response = await fetch(`/api/audit/document/${selectedDoc.id}`);
          // if (!response.ok) throw new Error('Failed to fetch document events');
          // const data: DocumentAuditEvent[] = await response.json();
          // setDocumentEvents(data);
          console.warn("API call for document events is mocked for now.");
          setDocumentEvents([
            {id: 1, event_type: "document_creation_event", username: "system", timestamp: new Date().toISOString(), data: { action_description: "Document created"}},
            {id: 2, event_type: "document_processing_started", username: "system", timestamp: new Date().toISOString(), data: { step: "OCR" }},
          ]);
        } catch (err) {
          console.error("Error fetching document events:", err);
          setDocumentEvents([]);
        } finally {
          setLoadingDocumentEvents(false);
        }
      };
      fetchDocumentEvents();
    }
  }, [selectedDoc, activeTab]);

  const handleSaveProcessedText = async () => {
    if (!selectedDoc || !parsedProcessedData?.results || !Array.isArray(parsedProcessedData.results)) return; // Use parsed data
    const pageData = parsedProcessedData.results.find(p => p.page_number === currentPageNumber); // Use parsed data
    if (!pageData) return;

    console.log("Saving processed text for doc ID:", selectedDoc.id, "Page:", currentPageNumber, "Text:", editedProcessedText);
    // TODO: Implement API call to PUT /api/documents/{selectedDoc.id}/processed_data (or similar)
    // The API might expect the whole processed_data array or just the text for a specific page.
    // For now, this is a mock.
    alert(`Save for page ${currentPageNumber} (Doc ID: ${selectedDoc.id}) is not yet implemented.`);
    // Optimistically update local state or refetch
    // const updatedProcessedData = selectedDoc.processed_data.map(p => 
    //   p.page_number === currentPageNumber ? { ...p, extracted_text: editedProcessedText } : p
    // );
    // setSelectedDoc(prev => prev ? { ...prev, processed_data: updatedProcessedData } : null);
    // setAllDocs(prevAllDocs => prevAllDocs.map(d => 
    //   d.id === selectedDoc.id ? { ...d, processed_data: updatedProcessedData } : d
    // ));
  };

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

  const renderPreview = (doc: Document | null) => {
    if (!doc) { 
      return <div className="p-4 text-gray-500">Select a document to view its preview.</div>;
    }
    if (loadingDetail && !doc.data_b64) { // Show loading if detail is loading and no data yet for selected doc
        return <div className="p-4 text-gray-500">Loading document preview...</div>;
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
    <div className="flex flex-col h-screen">
      {/* Fixed Search Bar at the top of the page might be better if it applies to the whole view or if sidebar is collapsible */}
      {/* For now, search is part of the sidebar as per original structure interpretation */}
      <div className="flex flex-grow overflow-hidden"> {/* This will contain sidebar and main content */}
        {/* Left Panel: Document List Sidebar */}
        <div className="w-1/3 border-r overflow-y-auto p-4 flex flex-col" style={{maxHeight: 'calc(100vh - 50px)'}}> {/* Assuming 50px for a top header/taskbar not part of this component */}
          <h1 className="text-xl font-bold mb-4 sticky top-0 bg-white z-10 pb-2">Documents</h1>
          <input
            type="text"
            placeholder="Search documents..."
            value={searchTerm}
            onChange={handleSearchChange}
            className="w-full p-2 border rounded mb-4 sticky top-12 bg-white z-10" /* Adjust top if header height changes */
          />
          <div className="flex-grow overflow-y-auto">
            {loadingList && <p>Loading document list...</p>}
            {error && !loadingList && <p className="text-red-500">{error}</p>}
            {!loadingList && filteredDocs.length === 0 && !error && <p>No documents found.</p>}
            <ul className="space-y-2">
              {filteredDocs.map(doc => (
                <li key={doc.id}
                    className={`p-2 rounded cursor-pointer hover:bg-gray-100 ${selectedDoc?.id === doc.id ? 'bg-blue-100 border-l-4 border-blue-500' : 'border border-gray-200'}`}
                    onClick={() => navigate(`/documents?docId=${doc.id}`)}>
                  <div className="font-semibold truncate">{doc.filename}</div>
                  <div className="text-xs text-gray-500">{doc.content_type} - {formatDate(doc.created_at)}</div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right Panel: Document Preview and Tabs */}
        <div className="w-2/3 p-4 flex flex-col bg-gray-50 overflow-y-auto">
          {selectedDoc ? (
            <>
              {/* Top Section: Document Preview */}
              <div className="mb-2 pb-2 border-b">
                  <h2 className="text-lg font-semibold truncate">{selectedDoc.filename}</h2>
                  <p className="text-sm text-gray-600">{selectedDoc.content_type} - Created: {formatDate(selectedDoc.created_at)}</p>
              </div>
              <div className="flex-grow border rounded bg-white overflow-auto min-h-[300px] mb-4">
                {renderPreview(selectedDoc)}
              </div>

              {/* Bottom Section: Tabs */}
              <div className="border-t pt-2">
                <div className="flex border-b mb-4">
                  <button 
                    className={`py-2 px-4 font-medium text-sm ${activeTab === 'info' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                    onClick={() => setActiveTab('info')}
                  >
                    Info & Email
                  </button>
                  <button 
                    className={`py-2 px-4 font-medium text-sm ${activeTab === 'results' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                    onClick={() => setActiveTab('results')}
                  >
                    Results & Edit
                  </button>
                  <button 
                    className={`py-2 px-4 font-medium text-sm ${activeTab === 'events' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                    onClick={() => setActiveTab('events')}
                  >
                    Events
                  </button>
                </div>

                {/* Tab Content */}
                <div>
                  {activeTab === 'info' && (
                    <div>
                      <h3 className="text-md font-semibold mb-2">Email Information</h3>
                      {loadingEmailSummary && <p>Loading email summary...</p>}
                      {emailSummary ? (
                        <div className="text-sm p-2 bg-blue-50 rounded cursor-pointer hover:bg-blue-100"
                             onClick={() => navigate(`/emails?emailId=${emailSummary.id}`)}>
                          <p><strong>Subject:</strong> {emailSummary.subject}</p>
                          <p><strong>Type:</strong> {emailSummary.type || 'N/A'}</p>
                          <p><strong>Summary:</strong> {emailSummary.short_description || 'N/A'}</p>
                          <p><strong>Date:</strong> {formatDate(emailSummary.received_at)}</p>
                        </div>
                      ) : (
                        !loadingEmailSummary && <p className="text-xs text-gray-500">No email summary available or document not linked to an email.</p>
                      )}
                    </div>
                  )}
                  {activeTab === 'results' && (
                    <div>
                      <h3 className="text-md font-semibold mb-2">Processed Text Results</h3>
                      {parsedProcessedData?.results && Array.isArray(parsedProcessedData.results) && parsedProcessedData.results.length > 0 ? (
                        <>
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center">
                              <label htmlFor="page-select" className="text-sm mr-2">Page:</label>
                              <select
                                id="page-select"
                                value={currentPageNumber}
                                onChange={(e) => setCurrentPageNumber(parseInt(e.target.value, 10))}
                                className="px-3 py-1 text-sm border rounded bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                              >
                                {(parsedProcessedData.results || []).map(page => (
                                  <option key={page.page_number} value={page.page_number}>
                                    {page.page_number}
                                  </option>
                                ))}
                              </select>
                              <span className="text-sm ml-2">
                                of {parsedProcessedData.results.length}
                              </span>
                            </div>
                            <div>
                              <button
                                onClick={() => setCurrentPageNumber(prev => Math.max(1, prev - 1))}
                                disabled={currentPageNumber === 1}
                                className="px-3 py-1 text-sm border rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50 mr-2"
                              >
                                Previous
                              </button>
                              <button
                                onClick={() => setCurrentPageNumber(prev => Math.min(parsedProcessedData.results!.length, prev + 1))}
                                disabled={currentPageNumber === parsedProcessedData.results.length}
                                className="px-3 py-1 text-sm border rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                              >
                                Next
                              </button>
                            </div>
                          </div>
                          <textarea
                            value={editedProcessedText}
                            onChange={(e) => setEditedProcessedText(e.target.value)}
                            className="w-full h-60 p-2 border rounded text-sm whitespace-pre-wrap" // whitespace-pre-wrap to respect newlines and wrap text
                            placeholder="Processed text for the current page will appear here. You can edit it."
                          />
                          <button
                            onClick={handleSaveProcessedText}
                            className="mt-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm">
                            Save Changes for Page {currentPageNumber}
                          </button>
                        </>
                      ) : (
                        <p className="text-xs text-gray-500">No processed data available for this document.</p>
                      )}
                    </div>
                  )}
                  {activeTab === 'events' && (
                    <div>
                      <h3 className="text-md font-semibold mb-2">Document Events</h3>
                      {loadingDocumentEvents && <p>Loading document events...</p>}
                      {documentEvents.length > 0 ? (
                        <ul className="list-disc pl-5 text-sm">
                          {documentEvents.map(event => (
                            <li key={event.id} className="mb-1">
                              <strong>{formatDate(event.timestamp)}:</strong> [{event.event_type}] by {event.username} - 
                              <span className="text-gray-600 cursor-pointer hover:underline" title={JSON.stringify(event.data, null, 2)}>View Data</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        !loadingDocumentEvents && <p className="text-xs text-gray-500">No events found for this document.</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-auto pt-4 flex justify-end"> {/* This Proceed button might be redundant or need rethinking in this new layout */}
                  <button
                      onClick={() => navigate(`/validation?docId=${selectedDoc.id}`)}
                      className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm">
                      Proceed to Validation Page
                  </button>
              </div>
            </>
          ) : (
            <div className="flex-grow flex items-center justify-center text-gray-500">
              {loadingList || loadingDetail ? "Loading documents..." : "Select a document from the list to view its details."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Documents;
