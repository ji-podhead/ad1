import * as React from 'react';
import { useState, useEffect } from 'react';
// import Calendar from '../components/Calendar'; // Calendar component can be re-integrated if date filtering is added for API

// Define the ProcessingTask interface based on backend Pydantic model
interface ProcessingTask {
  id: number; // from tasks table
  email_id: number;
  status: string;
  created_at: string; // ISO date string
  updated_at: string; // ISO date string
  // Fields from emails table
  email_subject?: string | null;
  email_sender?: string | null;
  email_body?: string | null;
  email_received_at?: string | null; // ISO date string
  email_label?: string | null;
  workflow_type?: string | null;
  email_short_description?: string | null;
}

// Consistent status styling, ensure keys are lowercase to match backend or use .toLowerCase() when accessing
const statusStyles: Record<string, string> = {
  pending: 'bg-gray-200 text-gray-800',
  processing: 'bg-blue-200 text-blue-800',
  validated: 'bg-green-200 text-green-800',
  aborted: 'bg-red-200 text-red-800',
  failed: 'bg-orange-200 text-orange-800', // Example for another potential status
  'needs validation': 'bg-yellow-200 text-yellow-900', // For "Needs Validation" status
};

// Consistent status icons
const statusIcons: Record<string, string> = {
  pending: '⏳',
  processing: '⏳',
  validated: '✅',
  aborted: '❌',
  failed: '🔥',
  'needs validation': '⚠️',
};

const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState<ProcessingTask[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/processing_tasks');
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to fetch tasks: ${response.status} ${response.statusText} - ${errorText}`);
      }
      const data: ProcessingTask[] = await response.json();
      setTasks(data);
    } catch (err: any) {
      setError(err.message);
      console.error("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleTaskAction = async (taskId: number, action: 'validate' | 'abort') => {
    setError(null); // Clear previous errors specific to actions
    try {
      const response = await fetch(`/api/processing_tasks/${taskId}/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP error ${response.status}` }));
        throw new Error(`Action ${action} failed for task ${taskId}: ${errorData.detail || response.statusText}`);
      }
      // Refresh tasks list to show updated status
      await fetchTasks();
    } catch (err: any) {
      setError(err.message); // Set action-specific error
      console.error(`Error during ${action} action for task ${taskId}:`, err);
      alert(`Error performing action: ${err.message}`); // Provide feedback to the user
    }
  };

  const formatDate = (dateString?: string | null) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Email Processing Tasks</h1>

      {/* Optional: Button to manually refresh tasks */}
      <div className="mb-4">
        <button
          className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded text-sm"
          onClick={fetchTasks}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh Tasks'}
        </button>
      </div>

      {loading && tasks.length === 0 && <p>Loading tasks...</p>}
      {error && <p className="text-red-500 p-4 bg-red-100 border border-red-400 rounded">Error: {error}</p>}

      {!loading && !error && tasks.length === 0 && <p>No tasks found.</p>}

      {!loading && tasks.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border bg-white rounded shadow min-w-full">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Email Subject</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Sender</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Email Short Description</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Status</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Workflow Type</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Email Received</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Task Updated</th>
                <th className="p-3 text-left text-sm font-semibold text-gray-700">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr key={task.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 text-sm text-gray-700">{task.email_subject || 'N/A'}</td>
                  <td className="p-3 text-sm text-gray-700">{task.email_sender || 'N/A'}</td>
                  <td className="p-3 text-sm text-gray-700 truncate max-w-xs" title={task.email_short_description || undefined}>{task.email_short_description || 'N/A'}</td>
                  <td className="p-3 text-sm">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1 ${statusStyles[task.status.toLowerCase()] || statusStyles['pending']}`}>
                      <span>{statusIcons[task.status.toLowerCase()] || statusIcons['pending']}</span> {task.status}
                    </span>
                  </td>
                  <td className="p-3 text-sm text-gray-700">{task.workflow_type || 'N/A'}</td>
                  <td className="p-3 text-sm text-gray-700">{formatDate(task.email_received_at)}</td>
                  <td className="p-3 text-sm text-gray-700">{formatDate(task.updated_at)}</td>
                  <td className="p-3 text-sm flex gap-2">
                    <button
                      className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-xs font-medium disabled:opacity-50"
                      onClick={() => handleTaskAction(task.id, 'validate')}
                      disabled={task.status.toLowerCase() === 'validated' || task.status.toLowerCase() === 'aborted'}
                    >
                      Validate
                    </button>
                    <button
                      className="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-xs font-medium disabled:opacity-50"
                      onClick={() => handleTaskAction(task.id, 'abort')}
                      disabled={task.status.toLowerCase() === 'validated' || task.status.toLowerCase() === 'aborted'}
                    >
                      Abort
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Tasks;
