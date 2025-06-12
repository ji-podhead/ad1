import React, { useState, useEffect, useMemo } from 'react';

interface AuditEntry {
  id: number;
  event_type: string;
  username: string;
  timestamp: string;
  data: Record<string, any> | null;
}

const Audit: React.FC = () => {
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [filteredLogs, setFilteredLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [userFilter, setUserFilter] = useState<string>("");
  const [eventTypeFilter, setEventTypeFilter] = useState<string>(""); // Changed from actionFilter
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false); // For data details modal
  const [modalContent, setModalContent] = useState<string>(""); // Content for the modal

  const fetchAuditLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/audit');
      if (!response.ok) {
        throw new Error(`Failed to fetch audit logs: ${response.statusText}`);
      }
      const data: AuditEntry[] = await response.json();
      setAuditLogs(data);
      // setFilteredLogs(data); // Initial population, will be handled by useEffect
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unknown error occurred');
      }
      console.error("Error fetching audit logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, []);

  useEffect(() => {
    let logs = auditLogs;
    if (userFilter) {
      logs = logs.filter(log =>
        log.username.toLowerCase().includes(userFilter.toLowerCase())
      );
    }
    if (eventTypeFilter) { // Changed from actionFilter
      logs = logs.filter(log =>
        log.event_type.toLowerCase().includes(eventTypeFilter.toLowerCase()) // Changed from log.action
      );
    }
    setFilteredLogs(logs);
  }, [auditLogs, userFilter, eventTypeFilter]); // Changed from actionFilter

  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Audit Trail</h1>
      </header>

      <div className="mb-6 p-4 bg-white shadow rounded-lg">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <label htmlFor="userFilter" className="block text-sm font-medium text-gray-700 mb-1">Filter by User</label>
            <input
              type="text"
              id="userFilter"
              value={userFilter}
              onChange={e => setUserFilter(e.target.value)}
              placeholder="Enter username..."
              className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="eventTypeFilter" className="block text-sm font-medium text-gray-700 mb-1">Filter by Event Type</label> {/* Changed from Action */}
            <input
              type="text"
              id="eventTypeFilter" // Changed from actionFilter
              value={eventTypeFilter} // Changed from actionFilter
              onChange={e => setEventTypeFilter(e.target.value)} // Changed from setActionFilter
              placeholder="Enter event type keyword..." // Changed placeholder text
              className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            />
          </div>
          <button
            onClick={fetchAuditLogs}
            disabled={loading}
            className="w-full md:w-auto justify-self-start md:justify-self-end px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            {loading ? 'Refreshing...' : 'Refresh Logs'}
          </button>
        </div>
      </div>

      {loading && <div className="text-center py-10 text-gray-500">Loading audit logs...</div>}
      {error && <div className="text-center py-10 text-red-600 bg-red-50 p-4 rounded-md">Error: {error}</div>}

      {!loading && !error && (
        <div className="overflow-x-auto bg-white shadow rounded-lg">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Event Type</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Data</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredLogs.length > 0 ? (
                filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{formatDate(log.timestamp)}</td>
                    <td className="px-6 py-4 whitespace-normal text-sm text-gray-900 max-w-xs truncate" title={log.event_type}>
                      {log.event_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{log.username}</td>
                    <td 
                      className="px-6 py-4 whitespace-nowrap text-sm text-blue-600 hover:underline cursor-pointer"
                      title={log.data ? JSON.stringify(log.data, null, 2) : 'No data'}
                      onClick={() => {
                        setModalContent(log.data ? JSON.stringify(log.data, null, 2) : 'No data available.');
                        setIsModalOpen(true);
                      }}
                    >
                      [View Details]
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-sm text-gray-500"> {/* Adjusted colSpan from 7 to 4 */}
                    {auditLogs.length === 0 ? "No audit logs found." : "No logs match your filters."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {/* Modal for Data Details */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex justify-center items-center">
          <div className="relative mx-auto p-5 border w-full max-w-2xl shadow-lg rounded-md bg-white">
            <div className="mt-3 text-center">
              <h3 className="text-lg leading-6 font-medium text-gray-900">Audit Log Data Details</h3>
              <div className="mt-2 px-7 py-3">
                <pre className="text-sm text-gray-700 bg-gray-100 p-4 rounded-md overflow-auto max-h-96 text-left whitespace-pre-wrap break-all">
                  {modalContent}
                </pre>
              </div>
              <div className="items-center px-4 py-3">
                <button
                  id="close-modal"
                  className="px-4 py-2 bg-indigo-500 text-white text-base font-medium rounded-md w-full shadow-sm hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  onClick={() => setIsModalOpen(false)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Audit;
