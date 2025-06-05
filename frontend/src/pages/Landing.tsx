// Landing page: Welcome, project info, and navigation links
import React from 'react';
import About from './About';
import { GoogleLogin } from '@react-oauth/google';

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
  const [aboutOpen, setAboutOpen] = React.useState(false);
  const [user, setUser] = React.useState<any>(null);
  const [clientId, setClientId] = React.useState<string | null>(null);

  React.useEffect(() => {
    const stored = localStorage.getItem('ad1_user');
    if (stored) setUser(JSON.parse(stored));
    fetch('/api/oauth-config')
      .then(async res => {
        if (!res.ok) throw new Error('Google OAuth config not found (HTTP ' + res.status + ')');
        const json = await res.json();
        if (!json.web || !json.web.client_id) {
          throw new Error('Google OAuth config missing web.client_id.');
        }
        setClientId(json.web.client_id);
      })
      .catch(err => setClientId('ERROR:' + (err?.message || err)));
  }, []);

  const handleLogin = (user: any) => {
    setUser(user);
    localStorage.setItem('ad1_user', JSON.stringify(user));
    // After Google login, ask backend for user info/roles
    fetch('/api/userinfo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, token: user.credential || null })
    })
      .then(res => res.json())
      .then(info => {
        // Optionally store roles/admin info in state if needed for UI
        setUser((u: any) => ({ ...u, ...info }));
        // Optionally: localStorage.setItem('ad1_userinfo', JSON.stringify(info));
      })
      .catch(() => {/* ignore, backend decides access */});
    window.location.href = '/inbox';
  };

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
      <div style={gradientBG} className="animate-gradient-move" />
      <div className="absolute inset-0 bg-gradient-to-br from-blue-100/60 via-pink-100/40 to-white/0 pointer-events-none" />
      <div className="z-10 flex flex-col items-center justify-center min-h-[70vh]">
        <div className="bg-white/90 rounded-3xl shadow-2xl p-10 max-w-xl w-full border border-blue-100 animate-fade-in-up">
          <h1 className="text-5xl md:text-6xl font-extrabold mb-4 text-blue-700 tracking-tight text-center" style={{ fontFamily: 'Orbitron, monospace' }}>Ad1</h1>
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
          {!user && clientId && !clientId.startsWith('ERROR:') && (
            <div className="w-full flex items-center justify-center">
              <GoogleLogin
                onSuccess={credentialResponse => {
                  if (!credentialResponse.credential) return;
                  const base64Url = credentialResponse.credential.split('.')[1];
                  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                  const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                  }).join(''));
                  const user = JSON.parse(jsonPayload);
                  handleLogin({
                    name: user.name,
                    email: user.email,
                    picture: user.picture,
                    hd: user.hd || null,
                  });
                }}
                onError={() => {
                  alert('Login Failed');
                }}
                useOneTap
              />
            </div>
          )}
          {!user && clientId && clientId.startsWith('ERROR:') && (
            <div className="w-full flex items-center justify-center text-red-600 text-sm font-semibold bg-red-50 border border-red-200 rounded p-4 mt-4">
              {clientId.replace('ERROR:', '')}
            </div>
          )}
          {user && (
            <div className="w-full flex flex-col items-center gap-2 mt-4">
              <img src={user.picture} alt="pfp" className="w-16 h-16 rounded-full border shadow" />
              <div className="font-semibold text-blue-700">{user.name}</div>
              <div className="text-xs text-gray-500">{user.email}</div>
            </div>
          )}
          <button className="mt-4 w-full text-xs text-blue-600 underline" onClick={() => setAboutOpen(true)}>About / Info</button>
        </div>
        <div className="mt-12 text-sm text-gray-400">&copy; 2025 ad1 – Secure Swiss Document Automation</div>
      </div>
      {aboutOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 relative animate-fade-in-up overflow-y-auto max-h-[90vh]">
            <button onClick={() => setAboutOpen(false)} className="absolute top-2 right-2 text-gray-400 hover:text-gray-700 text-2xl">×</button>
            <About />
          </div>
        </div>
      )}
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
