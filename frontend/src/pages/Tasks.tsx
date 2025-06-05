// Task Section: Overview of all processing tasks, their status, and actions (select, validate, abort, etc.).
import React, { useState } from 'react';

const demoTasks = [
  { id: 1, name: 'Registration_Form.pdf', status: 'Processing', assigned: 'catbot', created: '2025-06-03' },
  { id: 2, name: 'Case_Notes.docx', status: 'Needs Validation', assigned: 'user2', created: '2025-06-02' },
  { id: 3, name: 'Final_Report.pdf', status: 'Validated', assigned: 'user1', created: '2025-06-01' },
];

const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState(demoTasks);

  const handleAction = (id: number, action: string) => {
    setTasks(tasks.map(t => t.id === id ? { ...t, status: action } : t));
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Tasks</h1>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Name</th>
            <th className="p-2 text-left">Assigned</th>
            <th className="p-2 text-left">Created</th>
            <th className="p-2 text-left">Status</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(task => (
            <tr key={task.id} className="border-t">
              <td className="p-2">{task.name}</td>
              <td className="p-2">{task.assigned}</td>
              <td className="p-2">{task.created}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs ${task.status === 'Processing' ? 'bg-blue-200' : task.status === 'Needs Validation' ? 'bg-yellow-200' : 'bg-green-200'}`}>{task.status}</span>
              </td>
              <td className="p-2 flex gap-2">
                {task.status === 'Needs Validation' && (
                  <button className="bg-green-600 text-white px-2 py-1 rounded text-xs" onClick={() => handleAction(task.id, 'Validated')}>Validate</button>
                )}
                {task.status !== 'Validated' && (
                  <button className="bg-red-500 text-white px-2 py-1 rounded text-xs" onClick={() => handleAction(task.id, 'Aborted')}>Abort</button>
                )}
                {task.status === 'Processing' && (
                  <button className="bg-yellow-500 text-white px-2 py-1 rounded text-xs" onClick={() => handleAction(task.id, 'Needs Validation')}>Send to Validation</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Tasks;
