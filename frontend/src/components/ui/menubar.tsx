import * as React from "react"
import { Link, useLocation } from "react-router-dom"
import { GoogleLogin } from '@react-oauth/google';

export function Menubar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`flex items-center h-12 bg-white border-b shadow-sm px-4 ${className ?? ''}`} {...props} />
}

export function MenubarMenu({ children }: { children: React.ReactNode }) {
  return <div className="relative group">{children}</div>
}

export function MenubarTrigger({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }) {
  return <button className="px-4 py-2 bg-transparent border-none cursor-pointer font-semibold" {...props}>{children}</button>
}

export function MenubarContent({ children }: { children: React.ReactNode }) {
  return <div className="absolute left-0 mt-2 min-w-[180px] bg-white border rounded shadow-lg z-50 hidden group-hover:block">{children}</div>
}

export function MenubarItem({ to, children, onNav, ...props }: React.HTMLAttributes<HTMLDivElement> & { to?: string, onNav?: (e: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => void }) {
  const location = useLocation();
  const isActive = to && location.pathname === to;
  return (
    <Link to={to || "#"} onClick={onNav}>
      <div className={`px-4 py-2 hover:bg-blue-50 cursor-pointer ${isActive ? 'bg-blue-100 font-bold' : ''}`} {...props}>{children}</div>
    </Link>
  );
}

export function MenubarSeparator() {
  return <div className="my-1 border-t border-gray-200" />
}

export function MenubarShortcut({ children }: { children: React.ReactNode }) {
  return <span className="ml-2 text-xs text-gray-400">{children}</span>
}

import { useAuth } from "../../contexts/AuthContext"; // Import useAuth

// Main navigation bar for all English pages
export function MainMenubar() { // Removed props: user, onLogin, onLogout
  const { user, setUser, isLoading } = useAuth(); // Use AuthContext
  const [clientId, setClientId] = React.useState<string | null>(null); // Keep clientId for GoogleLogin if needed

  React.useEffect(() => {
    // Fetch clientId only if no user, as GoogleLogin button might be shown
    if (!user && !isLoading) { // also check isLoading to prevent fetching while auth state is resolving
      fetch('/api/oauth-config')
        .then(async res => {
          if (!res.ok) throw new Error('Google OAuth config not found (HTTP ' + res.status + ')');
          const json = await res.json();
          if (!json.web || !json.web.client_id) {
            throw new Error('Google OAuth config missing web.client_id.');
          }
          setClientId(json.web.client_id);
        })
        .catch(err => {
          console.error("Failed to fetch Google Client ID:", err);
          setClientId('ERROR:' + (err?.message || err));
        });
    } else if (user) {
      setClientId(null); // User is logged in, no need for client ID for login button
    }
  }, [user, isLoading]);
  const pages = [
    { to: "/", label: "Ad1" },
    { to: "/inbox", label: "Inbox" },
    { to: "/documents", label: "Documents" },
    { to: "/tasks", label: "Tasks" },
    { to: "/audit", label: "Audit" },
    { to: "/ipam", label: "IAM" },
    { to: "/chat", label: "Agent Chat" },
    { to: "/settings", label: "Settings" }, // Add Settings link
  ];
  // Determine if the User Management link should be shown
  const showUserManagementLink = user && user.is_admin;

  return (
    <div className="flex items-center h-12 bg-white border-b shadow-sm px-4">
      <div className="flex-1 flex">
        {pages.map(page => (
          <MenubarItem key={page.to} to={page.to}>{page.label}</MenubarItem>
        ))}
        {showUserManagementLink && (
          <MenubarItem key="/user-management" to="/user-management">User Management</MenubarItem>
        )}
      </div>
      <div className="flex items-center gap-2">
        {isLoading ? (
          <span className="text-xs text-gray-500">Loading...</span>
        ) : user && user.email ? (
          <>
            {/* User picture can be added if available in context's user object and needed */}
            {/* <img src={user.picture} alt="pfp" className="w-8 h-8 rounded-full border" title={user.email} /> */}
            <span className="text-xs text-blue-700 font-semibold ml-2" title={user.email}>
              {user.email}
              {user.roles && user.roles.length > 0 && ` (Roles: ${user.roles.join(', ')})`}
              {user.is_admin && !user.roles.includes('admin') && ' (Admin)'} {/* Show (Admin) if is_admin is true and not already in roles */}
            </span>
            <button onClick={() => setUser(null)} className="text-xs text-gray-500 hover:underline ml-2">Logout</button>
          </>
        ) : (
          clientId && clientId.startsWith('ERROR:') ?
            <span className="text-xs text-red-500" title={clientId}>Login Error</span> :
          clientId ? <GoogleLogin
            onSuccess={credentialResponse => {
              if (!credentialResponse.credential) return;
              const base64Url = credentialResponse.credential.split('.')[1];
              const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
              const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
              }).join(''));
              const decodedUser = JSON.parse(jsonPayload);
              // Set user with email, AuthContext will fetch roles/admin status
              setUser({ email: decodedUser.email, is_admin: false, roles: [] });
            }}
            onError={() => {
              alert('Login Failed');
            }}
            useOneTap
          /> : <span className="text-xs text-gray-500">Initializing Login...</span>
        )}
      </div>
    </div>
  );
}
