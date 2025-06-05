import * as React from 'react';
import { useState } from 'react';
import Calendar from '../components/Calendar';

// Task Section: Overview of all processing tasks, their status, and actions (select, validate, abort, etc.).
const allDemoTasks = [
  { id: 1, name: 'Registration_Form.pdf', status: 'Processing', assigned: 'catbot', created: '2025-06-03' },
  { id: 2, name: 'Case_Notes.docx', status: 'Needs Validation', assigned: 'user2', created: '2025-06-02' },
  { id: 3, name: 'Final_Report.pdf', status: 'Validated', assigned: 'user1', created: '2025-06-01' },
  { id: 4, name: 'Invoice_2025-06-01.pdf', status: 'Needs Validation', assigned: 'user3', created: '2025-06-01' },
  { id: 5, name: 'Contract_Scan.pdf', status: 'Processing', assigned: 'catbot', created: '2025-06-03' },
  { id: 6, name: 'Expense_Report.xlsx', status: 'Aborted', assigned: 'user2', created: '2025-06-02' },
  { id: 7, name: 'HR_Form.docx', status: 'Needs Validation', assigned: 'user4', created: '2025-06-03' },
  { id: 8, name: 'Legal_Review.pdf', status: 'Validated', assigned: 'user1', created: '2025-06-01' },
  { id: 9, name: 'Onboarding.pdf', status: 'Processing', assigned: 'catbot', created: '2025-06-03' },
  { id: 10, name: 'Offer_Letter.pdf', status: 'Needs Validation', assigned: 'user5', created: '2025-06-02' },
];

const statusStyles: Record<string, string> = {
  Processing: 'bg-blue-200 text-blue-800',
  'Needs Validation': 'bg-yellow-200 text-yellow-900',
  Validated: 'bg-green-200 text-green-800',
  Aborted: 'bg-red-200 text-red-800',
};

const statusIcons: Record<string, string> = {
  Processing: '⏳',
  'Needs Validation': '⚠️',
  Validated: '✅',
  Aborted: '❌',
};

const Tasks: React.FC = () => {
  const [calendarMode, setCalendarMode] = useState<'day' | 'week' | 'month'>('day');
  const [date, setDate] = useState('');
  const [tasks, setTasks] = useState(allDemoTasks);
  const [selected, setSelected] = useState<number[]>([]);

  // Filter tasks by selected date/week/month
  let filteredTasks = tasks;
  if (date) {
    if (calendarMode === 'day') {
      filteredTasks = tasks.filter(t => t.created === date);
    } else if (calendarMode === 'week') {
      // date format: 2025-W23
      const [year, week] = date.split('-W');
      filteredTasks = tasks.filter(t => {
        const d = new Date(t.created);
        const dYear = d.getFullYear();
        const dWeek = Math.ceil((((d.getTime() - new Date(dYear,0,1).getTime()) / 86400000) + new Date(dYear,0,1).getDay()+1)/7);
        return dYear.toString() === year && dWeek.toString().padStart(2, '0') === week;
      });
    } else if (calendarMode === 'month') {
      // date format: 2025-06
      filteredTasks = tasks.filter(t => t.created.slice(0,7) === date);
    }
  }

  const handleSelect = (id: number, checked: boolean) => {
    setSelected((prev) =>
      checked ? [...prev, id] : prev.filter((sid) => sid !== id)
    );
  };

  const handleSelectAll = (checked: boolean) => {
    setSelected(checked ? filteredTasks.filter(t => t.status === 'Needs Validation').map(t => t.id) : []);
  };

  const handleAction = (id: number, action: string) => {
    setTasks(tasks.map(t => t.id === id ? { ...t, status: action } : t));
  };

  // This would be a navigation in a real app
  const handleValidateSelected = () => {
    if (selected.length === 1) {
      window.location.href = `/validation?tasks=${selected[0]}`;
    } else if (selected.length > 1) {
      alert('Please select only one task to validate at a time.');
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Tasks</h1>
      <div className="mb-4 flex items-center gap-4 flex-wrap">
        <label className="font-medium">Zeitraum wählen:</label>
        <select
          className="border rounded px-2 py-1"
          value={calendarMode}
          onChange={e => { setCalendarMode(e.target.value as any); setDate(''); }}
        >
          <option value="day">Tag</option>
          <option value="week">Woche</option>
          <option value="month">Monat</option>
        </select>
        <Calendar value={date} onChange={setDate} mode={calendarMode} />
        <button
          className="text-xs text-gray-500 underline"
          onClick={() => setDate('')}
          disabled={!date}
        >Alle anzeigen</button>
      </div>
      <div className="mb-2 flex items-center gap-4">
        <input
          type="checkbox"
          checked={selected.length === filteredTasks.filter(t => t.status === 'Needs Validation').length && selected.length > 0}
          onChange={e => handleSelectAll(e.target.checked)}
        />
        <span className="text-sm">Select all needing validation</span>
        <button
          className="ml-4 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
          disabled={selected.length === 0}
          onClick={handleValidateSelected}
        >
          Validate Selected
        </button>
      </div>
      <table className="w-full border bg-white rounded shadow">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2 text-left">Select</th>
            <th className="p-2 text-left">Name</th>
            <th className="p-2 text-left">Assigned</th>
            <th className="p-2 text-left">Created</th>
            <th className="p-2 text-left">Status</th>
            <th className="p-2 text-left">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredTasks.map(task => (
            <tr key={task.id} className="border-t">
              <td className="p-2">
                {task.status === 'Needs Validation' && (
                  <input
                    type="checkbox"
                    checked={selected.includes(task.id)}
                    onChange={e => handleSelect(task.id, e.target.checked)}
                  />
                )}
              </td>
              <td className="p-2">{task.name}</td>
              <td className="p-2">{task.assigned}</td>
              <td className="p-2">{task.created}</td>
              <td className="p-2">
                <span className={`px-2 py-1 rounded text-xs inline-flex items-center gap-1 ${statusStyles[task.status] || ''}`}>
                  <span>{statusIcons[task.status] || ''}</span> {task.status}
                </span>
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
