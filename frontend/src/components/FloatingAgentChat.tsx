// FloatingAgentChat.tsx
// Floating chat window with toggle button, visible on all pages after login
import React, { useState } from 'react';
import AgentChat from '../pages/AgentChat';

// TODO: Replace with real login state
const isLoggedIn = true;

const FloatingAgentChat: React.FC = () => {
  const [open, setOpen] = useState(false);
  if (!isLoggedIn) return null;
  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed z-50 bottom-6 right-6 bg-pink-600 hover:bg-pink-700 text-white rounded-full shadow-lg w-14 h-14 flex items-center justify-center text-2xl focus:outline-none"
        aria-label={open ? 'Chat schließen' : 'Chat öffnen'}
      >
        💬
      </button>
      {open && (
        <div className="fixed z-50 bottom-24 right-6 w-96 max-w-full bg-white rounded-xl shadow-2xl border border-pink-200 animate-fade-in-up">
          <AgentChat />
        </div>
      )}
    </>
  );
};

export default FloatingAgentChat;
