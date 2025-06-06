// Layout component for consistent page structure (optional, can be extended with nav/sidebar)
import * as React from 'react';
import { MainMenubar } from './ui/menubar';
import FloatingAgentChat from './FloatingAgentChat';
import { useLocation, useNavigate } from 'react-router-dom'; // Added useNavigate
import { useEffect, useState } from 'react'; // Removed useState for user
import { GoogleOAuthProvider } from '@react-oauth/google';
import LoginModal from './LoginModal';
import { useAuth } from '../contexts/AuthContext'; // Import useAuth
import { Toaster } from 'sonner'; // Import Toaster

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate(); // For programmatic navigation
  const { user, isLoading, setUser } = useAuth(); // Use AuthContext
  const [oauthClientId, setOauthClientId] = useState<string | null>(null); // For GoogleOAuthProvider
  const hideFloatingChat = location.pathname === '/chat';

  useEffect(() => {
    // Fetch client ID for GoogleOAuthProvider, only if not already fetched or if login might be displayed
    // This is for the @react-oauth/google components like GoogleLogin used in Menubar or LoginModal
    if (!oauthClientId || (!user && !isLoading)) {
      fetch('/api/oauth-config')
        .then(async res => {
          if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`Google OAuth config not found (HTTP ${res.status}): ${errorText}`);
          }
          const json = await res.json();
          if (!json.web || !json.web.client_id) {
            throw new Error('Google OAuth config missing web.client_id.');
          }
          setOauthClientId(json.web.client_id);
        })
        .catch(err => {
          console.error('Fetch error for /api/oauth-config:', err);
          setOauthClientId('ERROR:' + (err?.message || err));
        });
    }
  }, [user, isLoading, oauthClientId]);


  // Effect to handle redirection if not logged in
  useEffect(() => {
    if (!isLoading && !user && location.pathname !== '/') {
      console.log("User not loaded and not on landing, redirecting to /");
      navigate('/'); // Use navigate for client-side redirection
    }
  }, [user, isLoading, location.pathname, navigate]);

  // Render loading state or error for OAuth Client ID
  if (isLoading && !oauthClientId) { // If auth is loading AND we don't have client_id yet for login buttons
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        Loading authentication...
      </div>
    );
  }

  if (!oauthClientId && location.pathname === '/') {
    // On landing page, if client ID is not yet loaded for login button, show a minimal loading.
    // Or, if we want to ensure LoginModal can always show, this check might be too aggressive.
    // For now, let it pass to render LoginModal if user is null.
  } else if (!oauthClientId && !user) { // If not on landing, and no user, and no client ID for login modal
     return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        Initializing login provider...
      </div>
    );
  }


  if (oauthClientId && oauthClientId.startsWith('ERROR:')) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white border border-red-200 text-red-700 rounded-xl shadow-xl p-8 max-w-lg w-full text-center text-lg font-semibold animate-fade-in-up">
          {oauthClientId.replace('ERROR:', '')}
        </div>
      </div>
    );
  }

  // If user is not logged in and we are on the landing page, LoginModal will be shown.
  // If user is not logged in and NOT on landing, the useEffect above should have redirected.
  // If still loading oauthClientId for the LoginModal/GoogleLogin on landing, it's okay, they will appear once loaded.

  return (
    // Pass oauthClientId only if it's valid and loaded
    <GoogleOAuthProvider clientId={oauthClientId || "fallback_client_id_for_safety_should_not_be_used"}>
      <div className="min-h-screen bg-gray-50">
        <MainMenubar /> {/* user, onLogin, onLogout props are removed as MainMenubar uses AuthContext directly */}
        <main className="max-w-6xl mx-auto pt-[72px] pb-8 px-2">{children}</main>
        {!hideFloatingChat && user && user.email && <FloatingAgentChat />}
        {/* LoginModal should also use AuthContext if it needs to set user, or be purely for UI if MainMenubar handles login */}
        {/* For now, assume LoginModal might still be used on landing page. It needs to be updated to use AuthContext.setUser */}
        {!isLoading && !user && location.pathname === '/' && oauthClientId && !oauthClientId.startsWith('ERROR:') && (
          <LoginModal
            onLogin={(loggedInUser) => setUser({ email: loggedInUser.email, is_admin: false, roles: [] })}
          />
        )}
        <Toaster richColors position="top-right" /> {/* Add Toaster here */}
      </div>
    </GoogleOAuthProvider>
  );
};

export default Layout;
