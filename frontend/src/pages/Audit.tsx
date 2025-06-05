// Audit Trail page: View all actions and changes for compliance.
import React from 'react';

const demoAudit = [
	{ time: '2025-06-03 10:00', action: 'Email received', user: 'system' },
	{ time: '2025-06-03 10:01', action: 'Document uploaded', user: 'user1' },
	{ time: '2025-06-03 10:05', action: 'Agent processed document', user: 'catbot' },
	{ time: '2025-06-03 10:10', action: 'Validation started', user: 'user2' },
	{ time: '2025-06-03 10:15', action: 'Document validated & sent', user: 'user2' },
];

const Audit: React.FC = () => {
	return (
		<div className="p-6">
			<h1 className="text-2xl font-bold mb-4">Audit Trail</h1>
			<table className="w-full border bg-white rounded shadow">
				<thead>
					<tr className="bg-gray-100">
						<th className="p-2 text-left">Time</th>
						<th className="p-2 text-left">Action</th>
						<th className="p-2 text-left">User</th>
					</tr>
				</thead>
				<tbody>
					{demoAudit.map((log, i) => (
						<tr key={i} className="border-t">
							<td className="p-2">{log.time}</td>
							<td className="p-2">{log.action}</td>
							<td className="p-2">{log.user}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
};

export default Audit;
