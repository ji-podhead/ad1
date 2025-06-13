import * as React from 'react';
import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import DocumentDetailCard from '../components/DocumentDetailCard'; // Import the new component

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

// Unified Document interface (based on backend model and Documents.tsx)
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
  const [selectedTask, setSelectedTask] = useState<ProcessingTask | null>(null); // State for selected task
  const [loadingTasks, setLoadingTasks] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [allDocuments, setAllDocuments] = useState<Document[]>([]); // To filter documents by email_id
  const [loadingDocuments, setLoadingDocuments] = useState<boolean>(true);

  const navigate = useNavigate();
  const location = useLocation();

  const fetchTasks = async () => {
    setLoadingTasks(true);
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
      setLoadingTasks(false);
    }
  };

  // Fetch all documents
  useEffect(() => {
    const fetchDocuments = async () => {
      setLoadingDocuments(true);
      try {
        const response = await fetch('/api/documents');
        if (!response.ok) {
          throw new Error(`Failed to fetch documents: ${response.statusText}`);
        }
        const data: Document[] = await response.json();
        setAllDocuments(data);
        console.log("Fetched all documents:", data);
      } catch (err) {
        if (err instanceof Error) setError(err.message);
        else setError('An unknown error occurred while fetching documents');
        console.error("Error fetching documents:", err);
      } finally {
        setLoadingDocuments(false);
      }
    };
    fetchDocuments();
  }, []);

  useEffect(() => {
    fetchTasks();
  }, []);

  // Handle task selection based on URL or initial load
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const taskIdParam = params.get('taskId');

    if (taskIdParam) {
      const numericTaskId = parseInt(taskIdParam, 10);
      if (tasks.length > 0) {
        const foundTask = tasks.find(task => task.id === numericTaskId);
        setSelectedTask(foundTask || null);
        if (!foundTask) {
            setError(`Task with ID ${taskIdParam} not found.`);
        } else {
            setError(null); // Clear error if task is found
        }
      } else if (!loadingTasks) {
          // Tasks finished loading but the ID was not found
          setSelectedTask(null);
          setError(`Task with ID ${taskIdParam} not found.`);
      }
    } else {
      setSelectedTask(null);
      setError(null);
    }
  }, [location.search, tasks, loadingTasks]); // Depend on tasks and loadingTasks

  const handleTaskSelect = (taskId: number) => {
    navigate(`/tasks?taskId=${taskId}`);
  };

  const handleValidateTask = async () => {
    if (!selectedTask) return;
    console.log("Validating task with ID:", selectedTask.id);
    // TODO: Implement API call to POST /api/processing_tasks/{task_id}/validate
    alert(`Validate task ${selectedTask.id} is not yet implemented.`);
    // After successful validation, you might want to refetch tasks or update the task status locally
  };

  // Filter documents for the selected task's email
  const documentsForSelectedTask = selectedTask
    ? allDocuments.filter(doc => doc.email_id === selectedTask.email_id)
    : [];

  // Placeholder for rendering document details (will reuse logic from Documents.tsx)
  const renderDocumentDetails = (doc: Document) => {
    // This will be implemented in the next step, reusing logic from Documents.tsx
    return (
      <DocumentDetailCard key={doc.id} document={doc} />
    );
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
    <div className="flex flex-col h-screen">
      {/* Top Section: Task List (1/3 height) */}
      <div className="w-full overflow-y-auto p-4 border-b" style={{ height: '33.33%' }}>
        <h1 className="text-xl font-bold mb-4">Email Processing Tasks</h1>

        {/* Optional: Button to manually refresh tasks */}
        <div className="mb-4">
          <button
            className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded text-sm"
            onClick={fetchTasks}
            disabled={loadingTasks}
          >
            {loadingTasks ? 'Refreshing...' : 'Refresh Tasks'}
          </button>
        </div>

        {loadingTasks && tasks.length === 0 && <p>Loading tasks...</p>}
        {error && !loadingTasks && <p className="text-red-500 p-4 bg-red-100 border border-red-400 rounded">Error: {error}</p>}

        {!loadingTasks && !error && tasks.length === 0 && <p>No processing tasks found.</p>}

        {!loadingTasks && tasks.length > 0 && (
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
                  <tr key={task.id} className={`border-t hover:bg-gray-50 ${selectedTask?.id === task.id ? 'bg-blue-50' : ''}`}
                      onClick={() => handleTaskSelect(task.id)}>
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
                      {/* Removed individual Validate/Abort buttons from list */}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Bottom Section: Selected Task Details (2/3 height) */}
      <div className="flex-1 overflow-y-auto p-4">
        {selectedTask ? (
          <>
            <h2 className="text-lg font-semibold mb-4">Details for Task {selectedTask.id}</h2>
            {/* Email Information */}
            <div className="mb-4 p-3 border rounded bg-gray-100">
                <h3 className="text-md font-semibold mb-2">Email Information</h3>
                <p className="text-sm"><strong>Subject:</strong> {selectedTask.email_subject || 'N/A'}</p>
                <p className="text-sm"><strong>Sender:</strong> {selectedTask.email_sender || 'N/A'}</p>
                <p className="text-sm"><strong>Received At:</strong> {selectedTask.email_received_at ? new Date(selectedTask.email_received_at).toLocaleDateString() : 'N/A'}</p>
                <p className="text-sm"><strong>Label:</strong> {selectedTask.email_label || 'N/A'}</p>
                <p className="text-sm"><strong>Workflow Type:</strong> {selectedTask.workflow_type || 'N/A'}</p>
                <p className="text-sm"><strong>Description:</strong> {selectedTask.email_short_description || 'N/A'}</p>
            </div>

            {/* Documents associated with the email */}
            <div className="mb-4">
                <h3 className="text-md font-semibold mb-2">Associated Documents ({documentsForSelectedTask.length})</h3>
                {loadingDocuments && <p>Loading documents...</p>}
                {!loadingDocuments && documentsForSelectedTask.length === 0 && <p className="text-sm text-gray-500">No documents found for this email.</p>}
                {!loadingDocuments && documentsForSelectedTask.length > 0 && (
                    <div>
                        {/* Render document details here */}
                        {documentsForSelectedTask.map(doc => renderDocumentDetails(doc))}
                    </div>
                )}
            </div>

            {/* Validate Button */}
            <div className="mt-auto pt-4 border-t flex justify-end">
                <button
                    onClick={handleValidateTask}
                    className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm"
                    disabled={selectedTask.status.toLowerCase() === 'validated' || selectedTask.status.toLowerCase() === 'aborted'}
                >
                    Validate Task
                </button>
            </div>
          </>
        ) : (
          <div className="flex-grow flex items-center justify-center text-gray-500">
            {loadingTasks ? "Loading tasks..." : "Select a task from the list to view its details."}
          </div>
        )}
      </div>
    </div>
  );
};

export default Tasks;
