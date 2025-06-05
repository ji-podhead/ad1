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
    fetch('/gcp-oauth.keys.json')
      .then(res => res.json())
      .then(json => setClientId(json.web.client_id));
  }, []);

  const handleLogin = () => {
    // Replace with real Google OAuth
    const fakeUser = { name: 'Max Mustermann', email: 'max@example.com', picture: 'https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y' };
    setUser(fakeUser);
    localStorage.setItem('ad1_user', JSON.stringify(fakeUser));
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

  return (
    <GoogleOAuthProvider clientId={clientId}>
      <div className="min-h-screen bg-gray-50">
        <MainMenubar user={user} onLogin={handleLogin} onLogout={handleLogout} onNav={protectedNav} />
        <main className="max-w-6xl mx-auto pt-[72px] pb-8 px-2">{children}</main>
        {!hideFloatingChat && user && <FloatingAgentChat />}
        {!user && <LoginModal onLogin={handleLogin} />}
      </div>
    </GoogleOAuthProvider>
  );
};

export default Layout;
