// DocumentModal.tsx
import React from 'react';

interface DocumentModalProps {
  open: boolean;
  onClose: () => void;
  doc: any; // Still using 'any' for simplicity based on previous code, but ideally a specific Document interface
  previewContent: string | null; // Add prop for document content
  previewContentType: string | null; // Add prop for document content type
}

const DocumentModal: React.FC<DocumentModalProps> = ({ open, onClose, doc, previewContent, previewContentType }) => {
  if (!open || !doc) return null;

  // Determine how to display the content based on content type
  let contentElement = null;
  if (previewContent) {
    if (previewContentType?.startsWith('text/') || previewContentType === 'application/json') {
      // Display text-based content in a pre tag
      contentElement = (
        <pre className="mt-4 p-2 bg-gray-100 rounded overflow-auto max-h-60 text-sm">
          {previewContent}
        </pre>
      );
    } else if (previewContentType === 'application/pdf') {
      // Display PDF in an iframe
      // Need to create a Blob URL for the PDF content
      try {
        const byteCharacters = atob(previewContent); // Assuming previewContent is base64 for PDF
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: previewContentType });
        const pdfUrl = URL.createObjectURL(blob);
        contentElement = (
          <iframe src={pdfUrl} width="100%" height="400px" className="mt-4 border rounded"></iframe>
        );
      } catch (e) {
        console.error("Error creating PDF blob URL:", e);
        contentElement = <div className="mt-4 text-red-500">Error loading PDF preview.</div>;
      }
    } else if (previewContentType?.startsWith('image/')) {
       // Display images
       contentElement = (
         <img src={`data:${previewContentType};base64,${previewContent}`} alt="Document preview" className="mt-4 max-w-full h-auto" />
       );
    }
     else {
      // Fallback for other types
      contentElement = <div className="mt-4 text-gray-600">Preview not available for this document type ({previewContentType}).</div>;
    }
  } else if (!previewContent && doc.is_processed) {
       contentElement = <div className="mt-4 text-gray-600">Document processed, but no preview content available.</div>;
  } else if (!previewContent && !doc.is_processed) {
       contentElement = <div className="mt-4 text-gray-600">Document not yet processed. Preview will be available after processing.</div>;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 relative animate-fade-in-up">
        <button onClick={onClose} className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-2xl">×</button>
        <h2 className="text-xl font-bold mb-2">{doc.filename}</h2> {/* Use filename */}
        <div className="mb-2 text-sm text-gray-500">Created At: {doc.created_at}</div> {/* Use created_at */}
        <div className="mb-2 text-sm text-gray-500">Content Type: {doc.content_type}</div> {/* Use content_type */}
        <div className="mb-2 text-sm text-gray-500">Processed: {doc.is_processed ? 'Yes' : 'No'}</div> {/* Use is_processed */}

        {contentElement} {/* Display the determined content element */}

        <div className="flex gap-2 mt-4">
          {/* <button className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700" onClick={onClose}>Validate</button> */}
           <button className="bg-gray-300 text-gray-800 px-4 py-2 rounded hover:bg-gray-400" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
};

export default DocumentModal;
