// Layout component for consistent page structure (optional, can be extended with nav/sidebar)
import * as React from 'react';
import { MainMenubar } from './ui/menubar';
import FloatingAgentChat from './FloatingAgentChat';
import { useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { GoogleOAuthProvider } from '@react-oauth/google';
import LoginModal from './LoginModal';

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const [user, setUser] = useState<any>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const hideFloatingChat = location.pathname === '/chat';

  // Simpler Google OAuth mock (replace with real logic)
  useEffect(() => {
    const stored = localStorage.getItem('ad1_user');
    if (stored) setUser(JSON.parse(stored));
  }, []);

  useEffect(() => {
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
        setUser((u: any) => ({ ...u, ...info }));
      })
      .catch(() => {/* ignore, backend decides access */});
  };
  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('ad1_user');
  };

  // Block access to all except landing if not logged in
  if (!user && location.pathname !== '/') {
    window.location.href = '/';
    return null;
  }

  // Block navigation in Menubar if not logged in
  const protectedNav = (e: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => {
    if (!user) {
      e.preventDefault();
      window.location.href = '/';
    }
  };

  if (!clientId) return null;
  if (clientId && clientId.startsWith('ERROR:')) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white border border-red-200 text-red-700 rounded-xl shadow-xl p-8 max-w-lg w-full text-center text-lg font-semibold animate-fade-in-up">
          {clientId.replace('ERROR:', '')}
        </div>
      </div>
    );
  }

  return (
    <GoogleOAuthProvider clientId={clientId}>
      <div className="min-h-screen bg-gray-50">
        <MainMenubar user={user} onLogin={handleLogin} onLogout={handleLogout} />
        <main className="max-w-6xl mx-auto pt-[72px] pb-8 px-2">{children}</main>
        {!hideFloatingChat && user && <FloatingAgentChat />}
        {!user && <LoginModal onLogin={handleLogin} />}
      </div>
    </GoogleOAuthProvider>
  );
};

export default Layout;
