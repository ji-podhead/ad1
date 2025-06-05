// Validation page: Human-in-the-loop validation interface.
import * as React from 'react';
import { useState } from 'react';

const demoAudit = [
  { time: '2025-06-03 10:00', action: 'Document uploaded', user: 'user1' },
  { time: '2025-06-03 10:05', action: 'Agent processed document', user: 'catbot' },
  { time: '2025-06-03 10:10', action: 'Validation started', user: 'user2' },
];

const exampleImageUrl = "https://m.media-amazon.com/images/I/71u89vsuAeS.__AC_SX300_SY300_QL70_ML2_.jpg";
const examplePdfUrl = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"; // Placeholder PDF

const Validation: React.FC = () => {
  const [status, setStatus] = useState('Needs Validation');
  const [audit, setAudit] = useState(demoAudit);

  const handleAction = (action: string) => {
    setAudit([...audit, { time: new Date().toISOString().slice(0,16).replace('T',' '), action, user: 'user2' }]);
    if (action === 'Validated & sent') setStatus('Validated');
    if (action === 'Aborted') setStatus('Aborted');
    if (action === 'Restarted with prompt') setStatus('Processing');
  };

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
      <div>
        <h2 className="text-xl font-semibold mb-2 text-blue-700">Original Document</h2>
        <div className="border rounded p-4 bg-white shadow h-72 flex items-center justify-center text-gray-500 text-lg">
          <img src={exampleImageUrl} alt="Sick Note Example" className="max-h-60 max-w-full object-contain" />
        </div>
        <div className="flex gap-4 mt-4">
          <a href={exampleImageUrl} download target="_blank" rel="noopener noreferrer" className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">Download Image</a>
          <a href={examplePdfUrl} download target="_blank" rel="noopener noreferrer" className="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600">Download PDF</a>
        </div>
      </div>
      <div>
        <h2 className="text-xl font-semibold mb-2 text-green-700">Processed Result</h2>
        <div className="border rounded p-4 bg-white shadow mb-4 h-72 flex flex-col gap-2">
          <div><b>Extracted Name:</b> Max Muster</div>
          <div><b>Date of Birth:</b> 2001-01-01</div>
          <div><b>Handwriting:</b> "Integration successful"</div>
          <div className="mt-2 text-xs text-gray-400">Status: {status}</div>
        </div>
        <div className="flex gap-2 mb-4">
          <button className="bg-red-500 text-white px-4 py-2 rounded" onClick={() => handleAction('Aborted')}>Abort</button>
          <button className="bg-yellow-500 text-white px-4 py-2 rounded" onClick={() => handleAction('Restarted with prompt')}>Restart with Prompt</button>
          <button className="bg-green-600 text-white px-4 py-2 rounded" onClick={() => handleAction('Validated & sent')}>Validate & Send</button>
        </div>
        <div className="mt-4 text-sm text-gray-600">
          <b>Audit Trail:</b>
          <ul className="list-disc ml-4 mt-2">
            {audit.map((a, i) => (
              <li key={i}>{a.time} – {a.action} ({a.user})</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export default Validation;
