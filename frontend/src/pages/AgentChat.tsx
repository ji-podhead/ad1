// Agent Chat page: WebSocket chat to trigger workflows, ask for status, or interact with Catbot.
import React, { useState } from 'react';

const demoMessages = [
  { from: 'user', text: 'Trigger workflow for new document.' },
  { from: 'catbot', text: 'Workflow started. Processing document...' },
  { from: 'catbot', text: 'Document processed. Ready for validation.' },
];

const AgentChat: React.FC = () => {
  const [messages, setMessages] = useState(demoMessages);
  const [input, setInput] = useState('');

  const sendMessage = () => {
    if (!input.trim()) return;
    setMessages([...messages, { from: 'user', text: input }]);
    setInput('');
    // For demo, auto-reply
    setTimeout(() => setMessages(msgs => [...msgs, { from: 'catbot', text: 'Received: ' + input }]), 800);
  };

  return (
    <div className="p-6 max-w-xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Agent Chat</h1>
      <div className="border rounded bg-white shadow p-4 h-64 overflow-y-auto flex flex-col gap-2 mb-4">
        {messages.map((msg, i) => (
          <div key={i} className={msg.from === 'user' ? 'text-right' : 'text-left'}>
            <span className={`inline-block px-3 py-2 rounded ${msg.from === 'user' ? 'bg-blue-100 text-blue-900' : 'bg-gray-200 text-gray-800'}`}>{msg.text}</span>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="border rounded px-3 py-2 flex-1"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Type a message..."
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
        />
        <button className="bg-blue-600 text-white px-4 py-2 rounded" onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
};

export default AgentChat;
