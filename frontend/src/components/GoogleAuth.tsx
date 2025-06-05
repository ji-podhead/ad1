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
  const res = await fetch('/gcp-oauth.keys.json');
  const json = await res.json();
  return json.web.client_id;
}

export const GoogleLoginButton: React.FC<{ onSuccess: (user: any) => void }> = ({ onSuccess }) => {
  useEffect(() => {
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
              });
            },
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
