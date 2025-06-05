// Landing page: Welcome, project info, and navigation links
import React from 'react';

const gradientBG = {
  background: 'linear-gradient(120deg, #a1c4fd 0%, #c2e9fb 50%, #fbc2eb 100%)',
  minHeight: '100vh',
  width: '100%',
  position: 'fixed' as 'fixed',
  zIndex: -1,
  top: 0,
  left: 0,
  animation: 'gradientMove 10s ease-in-out infinite alternate',
};

const Landing: React.FC = () => {
  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
      <div style={gradientBG} className="animate-gradient-move" />
      <div className="absolute inset-0 bg-gradient-to-br from-blue-100/60 via-pink-100/40 to-white/0 pointer-events-none" />
      <div className="z-10 flex flex-col items-center justify-center min-h-[70vh]">
        <div className="bg-white/90 rounded-3xl shadow-2xl p-10 max-w-xl w-full border border-blue-100 animate-fade-in-up">
          <h1 className="text-4xl md:text-5xl font-extrabold mb-4 text-blue-700 tracking-tight text-center font-mono drop-shadow-lg">ad1</h1>
          <p className="text-lg text-gray-700 mb-6 text-center">
            <span className="font-bold text-blue-600">Automated Email & Document Processing</span><br/>
            Secure, compliant, and efficient document workflows for Swiss/EU requirements.<br/>
            Ingest emails, process documents, validate with a human-in-the-loop, and track everything with full audit trails.
          </p>
          <div className="flex flex-wrap gap-3 justify-center mb-6">
            <a href="/inbox" className="bg-blue-600 text-white px-5 py-2 rounded shadow hover:bg-blue-700 transition">Inbox</a>
            <a href="/documents" className="bg-green-600 text-white px-5 py-2 rounded shadow hover:bg-green-700 transition">Documents</a>
            <a href="/validation" className="bg-yellow-500 text-white px-5 py-2 rounded shadow hover:bg-yellow-600 transition">Validation</a>
            <a href="/tasks" className="bg-purple-600 text-white px-5 py-2 rounded shadow hover:bg-purple-700 transition">Tasks</a>
            <a href="/audit" className="bg-gray-700 text-white px-5 py-2 rounded shadow hover:bg-gray-800 transition">Audit Trail</a>
            <a href="/chat" className="bg-pink-600 text-white px-5 py-2 rounded shadow hover:bg-pink-700 transition">Agent Chat</a>
          </div>
          <button className="w-full flex items-center justify-center gap-2 bg-white border border-gray-300 rounded px-4 py-2 shadow hover:bg-gray-50 transition text-gray-700 font-semibold text-lg">
            <svg width="24" height="24" viewBox="0 0 48 48" className="inline-block mr-2"><g><path fill="#4285F4" d="M43.611 20.083H42V20H24v8h11.303C33.962 32.833 29.418 36 24 36c-6.627 0-12-5.373-12-12s5.373-12 12-12c2.803 0 5.377.99 7.413 2.626l6.293-6.293C34.583 5.527 29.584 3 24 3 12.954 3 4 11.954 4 23s8.954 20 20 20c11.046 0 20-8.954 20-20 0-1.341-.138-2.651-.389-3.917z"/><path fill="#34A853" d="M6.306 14.691l6.571 4.819C14.655 16.104 19.008 13 24 13c2.803 0 5.377.99 7.413 2.626l6.293-6.293C34.583 5.527 29.584 3 24 3c-7.732 0-14.41 4.41-17.694 10.691z"/><path fill="#FBBC05" d="M24 43c5.356 0 10.207-1.843 13.994-4.994l-6.481-5.309C29.418 36 24 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45z"/><path fill="#EA4335" d="M43.611 20.083H42V20H24v8h11.303C34.62 32.254 29.418 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45c5.356 0 10.207-1.843 13.994-4.994l-6.481-5.309C29.418 36 24 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45z"/></g></svg>
            Sign in with Google
          </button>
        </div>
        <div className="mt-12 text-sm text-gray-400">&copy; 2025 ad1 – Secure Swiss Document Automation</div>
      </div>
      <style>{`
        @keyframes gradientMove {
          0% { background-position: 0% 50%; }
          100% { background-position: 100% 50%; }
        }
        .animate-gradient-move {
          background-size: 200% 200%;
          animation: gradientMove 10s ease-in-out infinite alternate;
        }
        .animate-fade-in-up {
          animation: fadeInUp 1s cubic-bezier(.39,.575,.565,1) both;
        }
        @keyframes fadeInUp {
          0% { opacity: 0; transform: translateY(40px); }
          100% { opacity: 1; transform: none; }
        }
      `}</style>
    </div>
  );
};

export default Landing;
