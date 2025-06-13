import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

// Unified Document interface (based on backend model)
interface Document {
  id: number;
  filename: string;
  content_type: string;
  data_b64: string | null;
  created_at: string;
  is_processed: boolean;
  email_id?: number;
  processed_data?: string | null;
}

interface DocumentDetailCardProps {
  document: Document;
  // Add other props if needed, e.g., for handling editing or navigation
}

const DocumentDetailCard: React.FC<DocumentDetailCardProps> = ({ document }) => {
  const [parsedProcessedData, setParsedProcessedData] = useState<{ filename: string; results: Array<{ page_number: number; extracted_text: string; error?: string }> } | null>(null);
  const [currentPageNumber, setCurrentPageNumber] = useState<number>(1);
  const [editedProcessedText, setEditedProcessedText] = useState<string>("");
  const [error, setError] = useState<string | null>(null); // Local error state for parsing

  const navigate = useNavigate();

  // Parse processed_data when the document prop changes
  useEffect(() => {
    let firstPageText = "";
    let parsedData = null;
    setError(null); // Clear previous errors

    if (document.processed_data && typeof document.processed_data === 'string' && document.processed_data.trim() !== '' && document.processed_data.trim().toLowerCase() !== 'null') {
      try {
        parsedData = JSON.parse(document.processed_data);
        if (parsedData && typeof parsedData === 'object' && parsedData.results && Array.isArray(parsedData.results)) {
          setParsedProcessedData(parsedData);
          if (parsedData.results.length > 0) {
            firstPageText = parsedData.results[0].extracted_text;
          }
        } else {
          console.warn("Processed data is not in expected format (missing 'results' array):", parsedData);
          setParsedProcessedData(null);
          setError("Processed data is not in the expected format.");
        }
      } catch (e) {
        console.error("Error parsing processed_data JSON:", e);
        setParsedProcessedData(null);
        setError("Error parsing processed data for this document.");
      }
    } else {
      setParsedProcessedData(null);
      console.log("No valid processed_data string found for parsing.");
    }
    setEditedProcessedText(firstPageText);
    setCurrentPageNumber(1); // Reset to first page when document changes
  }, [document]);

  // Update editedProcessedText when currentPageNumber or parsedProcessedData changes
  useEffect(() => {
    if (parsedProcessedData?.results && Array.isArray(parsedProcessedData.results) && parsedProcessedData.results.length > 0) {
      const pageData = parsedProcessedData.results.find(p => p.page_number === currentPageNumber);
      setEditedProcessedText(pageData ? pageData.extracted_text : "");
    } else {
        setEditedProcessedText("");
    }
  }, [parsedProcessedData, currentPageNumber]);

  const renderPreview = (doc: Document) => {
    if (!doc.data_b64) {
        return <div className="p-4 text-gray-500">Preview data is not available.</div>;
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

  const handleSaveProcessedText = async () => {
    if (!document || !parsedProcessedData?.results || !Array.isArray(parsedProcessedData.results)) return; // Use parsed data
    const pageData = parsedProcessedData.results.find(p => p.page_number === currentPageNumber); // Use parsed data
    if (!pageData) return;

    console.log("Saving processed text for doc ID:", document.id, "Page:", currentPageNumber, "Text:", editedProcessedText);
    // TODO: Implement API call to PUT /api/documents/{document.id}/processed_data (or similar)
    // The API might expect the whole processed_data array or just the text for a specific page.
    // For now, this is a mock.
    alert(`Save for page ${currentPageNumber} (Doc ID: ${document.id}) is not yet implemented.`);
    // Optimistically update local state or refetch
    // const updatedProcessedData = selectedDoc.processed_data.map(p => 
    //   p.page_number === currentPageNumber ? { ...p, extracted_text: editedProcessedText } : p
    // );
    // setSelectedDoc(prev => prev ? { ...prev, processed_data: updatedProcessedData } : null);
    // setAllDocs(prevAllDocs => prevAllDocs.map(d => 
    //   d.id === selectedDoc.id ? { ...d, processed_data: updatedProcessedData } : d
    // ));
  };

  return (
    <div className="border rounded p-4 mb-4 bg-white shadow-sm">
      <h3 className="text-md font-semibold mb-2">Document: {document.filename}</h3>
      <p className="text-sm text-gray-600 mb-2">Type: {document.content_type} - Processed: {document.is_processed ? 'Yes' : 'No'}</p>

      {/* Document Preview */}
      <div className="flex-grow border rounded bg-gray-50 overflow-auto min-h-[200px] max-h-[400px] mb-4">
        {renderPreview(document)}
      </div>

      {/* Processed Data Section */}
      <div>
        <h4 className="text-md font-semibold mb-2">Processed Text Results</h4>
        {error && <p className="text-red-500 text-sm mb-2">Error: {error}</p>}
        {parsedProcessedData?.results && Array.isArray(parsedProcessedData.results) && parsedProcessedData.results.length > 0 ? (
          <>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center">
                <label htmlFor={`page-select-${document.id}`} className="text-sm mr-2">Page:</label>
                <select
                  id={`page-select-${document.id}`}
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
              className="w-full h-40 p-2 border rounded text-sm whitespace-pre-wrap" // whitespace-pre-wrap to respect newlines and wrap text
              placeholder="Processed text for the current page will appear here. You can edit it."
            />
            <button
              onClick={handleSaveProcessedText}
              className="mt-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm">
              Save Changes for Page {currentPageNumber}
            </button>
          </>
        ) : (parsedProcessedData === null && document.is_processed) ? (
             <p className="text-xs text-gray-500">Processed data is available but could not be parsed or is not in the expected format.</p>
        ) : (
          <p className="text-xs text-gray-500">No processed data available for this document.</p>
        )}
      </div>

      {/* Link to full Documents page for this specific document */}
      <div className="mt-4 text-right">
        <button
          onClick={() => navigate(`/documents?docId=${document.id}`)}
          className="text-blue-600 hover:underline text-sm"
        >
          View/Edit in Documents Page
        </button>
      </div>
    </div>
  );
};

export default DocumentDetailCard;
