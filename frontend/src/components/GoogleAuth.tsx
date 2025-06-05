// GoogleAuth.tsx
import React, { useEffect } from 'react';

declare global {
  interface Window {
    google?: any;
  }
}

export function loadGoogleScript() {
  if (document.getElementById('google-client-script')) return;
  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.id = 'google-client-script';
  document.body.appendChild(script);
}

export async function getGoogleClientId(): Promise<string> {
  try {
    const res = await fetch('/api/oauth-config', { cache: 'no-store' });
    if (!res.ok) {
      throw new Error('Google OAuth config not found (HTTP ' + res.status + ')');
    }
    const json = await res.json();
    if (!json.web || !json.web.client_id) {
      throw new Error('Google OAuth config missing web.client_id.');
    }
    return json.web.client_id;
  } catch (err: any) {
    // Optionally log error
    throw new Error(
      'Failed to load Google OAuth config: ' + (err?.message || err)
    );
  }
}

export const GoogleLoginButton: React.FC<{ onSuccess: (user: any) => void }> = ({ onSuccess }) => {
  useEffect(() => {
    console.log('GoogleLoginButton rendered');
    getGoogleClientId().then(clientId => {
      loadGoogleScript();
      const interval = setInterval(() => {
        if (window.google && clientId) {
          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: (response: any) => {
              // decode JWT
              const base64Url = response.credential.split('.')[1];
              const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
              const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
              }).join(''));
              const user = JSON.parse(jsonPayload);
              onSuccess({
                name: user.name,
                email: user.email,
                picture: user.picture,
                hd: user.hd || null,
              });
            },
            ux_mode: 'redirect',
            login_uri: window.location.origin + '/inbox',
            // No 'hd' restriction, allow all Google accounts (including Workspace)
          });
          window.google.accounts.id.renderButton(
            document.getElementById('google-login-btn')!,
            { theme: 'outline', size: 'large', width: 260 }
          );
          clearInterval(interval);
        }
      }, 100);
    });
  }, [onSuccess]);

  return <div id="google-login-btn" className="flex justify-center" />;
};
