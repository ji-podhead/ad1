// Validation page: Human-in-the-loop validation interface.
import * as React from 'react';
import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const demoTasks = [
  { id: 1, name: 'Registration_Form.pdf', status: 'Processing', assigned: 'catbot', created: '2025-06-03' },
  { id: 2, name: 'Case_Notes.docx', status: 'Needs Validation', assigned: 'user2', created: '2025-06-02' },
  { id: 3, name: 'Final_Report.pdf', status: 'Validated', assigned: 'user1', created: '2025-06-01' },
];

const Validation: React.FC = () => {
  const location = useLocation();
  const [selectedTasks, setSelectedTasks] = useState<number[]>([]);
  const [tasks, setTasks] = useState(demoTasks);
  const [openTaskId, setOpenTaskId] = useState<number | null>(null);

  // Demo document/audit data for preview
  const demoAudit = [
    { time: '2025-06-03 10:00', action: 'Document uploaded', user: 'user1' },
    { time: '2025-06-03 10:05', action: 'Agent processed document', user: 'catbot' },
    { time: '2025-06-03 10:10', action: 'Validation started', user: 'user2' },
  ];
  const exampleImageUrl = "https://m.media-amazon.com/images/I/71u89vsuAeS.__AC_SX300_SY300_QL70_ML2_.jpg";
  const examplePdfUrl = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf";

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const ids = params.get('tasks');
    if (ids) {
      setSelectedTasks(ids.split(',').map(Number));
    }
  }, [location.search]);

  const selectedTaskObjs = tasks.filter(t => selectedTasks.includes(t.id));

  const handleAction = (action: string, taskId: number) => {
    // Implement the action handling logic here
    console.log(`Action: ${action} on Task ID: ${taskId}`);
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Validation</h1>
      {selectedTaskObjs.length === 0 ? (
        <div className="text-gray-500">No tasks selected for validation.</div>
      ) : (
        <div className="space-y-8">
          {selectedTaskObjs.map(task => (
            <div key={task.id} className="bg-white rounded shadow p-4 mb-4">
              <div className="flex items-center gap-4 mb-2">
                <span className="font-semibold text-blue-700">{task.name}</span>
                <span className="text-xs px-2 py-1 rounded bg-yellow-200 text-yellow-900">Needs Validation</span>
                <button
                  className="ml-auto bg-blue-100 text-blue-700 px-3 py-1 rounded text-xs hover:bg-blue-200"
                  onClick={() => setOpenTaskId(openTaskId === task.id ? null : task.id)}
                >
                  {openTaskId === task.id ? 'Close' : 'Open'}
                </button>
              </div>
              {openTaskId === task.id && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-4">
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
                      <div className="mt-2 text-xs text-gray-400">Status: Needs Validation</div>
                    </div>
                    <div className="flex gap-2 mb-4">
                      <button className="bg-red-500 text-white px-4 py-2 rounded" onClick={() => handleAction('Aborted', task.id)}>Abort</button>
                      <button className="bg-yellow-500 text-white px-4 py-2 rounded" onClick={() => handleAction('Restarted with prompt', task.id)}>Restart with Prompt</button>
                      <button className="bg-green-600 text-white px-4 py-2 rounded" onClick={() => handleAction('Validated & sent', task.id)}>Validate & Send</button>
                    </div>
                    <div className="mt-4 text-sm text-gray-600">
                      <b>Audit Trail:</b>
                      <ul className="list-disc ml-4 mt-2">
                        {demoAudit.map((a, i) => (
                          <li key={i}>{a.time} – {a.action} ({a.user})</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Validation;
