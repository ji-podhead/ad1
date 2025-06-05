import React from 'react';
import { GoogleLogin } from '@react-oauth/google';

const LoginModal: React.FC<{ onLogin: (user: any) => void }> = ({ onLogin }) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 relative animate-fade-in-up flex flex-col items-center">
        <h2 className="text-xl font-bold mb-4 text-blue-700">Sign in with Google</h2>
        <GoogleLogin
          onSuccess={credentialResponse => {
            if (!credentialResponse.credential) return;
            const base64Url = credentialResponse.credential.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
              return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            const user = JSON.parse(jsonPayload);
            onLogin({
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
    </div>
  );
};

export default LoginModal;
