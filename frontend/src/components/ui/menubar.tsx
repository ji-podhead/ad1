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

// Main navigation bar for all English pages
export function MainMenubar({ user, onLogin, onLogout }: { user?: any, onLogin?: (user: any) => void, onLogout?: () => void }) {
  const [clientId, setClientId] = React.useState<string | null>(null);
  React.useEffect(() => {
    fetch('/gcp-oauth.keys.json')
      .then(res => res.json())
      .then(json => setClientId(json.web.client_id));
  }, []);
  const pages = [
    { to: "/", label: "Ad1" },
    { to: "/inbox", label: "Inbox" },
    { to: "/documents", label: "Documents" },
    { to: "/validation", label: "Validation" },
    { to: "/tasks", label: "Tasks" },
    { to: "/audit", label: "Audit" },
    { to: "/ipam", label: "IAM" },
    { to: "/chat", label: "Agent Chat" },
  ];
  return (
    <div className="flex items-center h-12 bg-white border-b shadow-sm px-4">
      <div className="flex-1 flex">
        {pages.map(page => (
          <MenubarItem key={page.to} to={page.to}>{page.label}</MenubarItem>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {user ? (
          <>
            <img src={user.picture} alt="pfp" className="w-8 h-8 rounded-full border" title={user.email} />
            <span className="text-xs text-blue-700 font-semibold ml-2">{user.name}</span>
            <button onClick={onLogout} className="text-xs text-gray-500 hover:underline ml-2">Logout</button>
          </>
        ) : (
          clientId && <GoogleLogin
            onSuccess={credentialResponse => {
              if (!credentialResponse.credential) return;
              const base64Url = credentialResponse.credential.split('.')[1];
              const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
              const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
              }).join(''));
              const user = JSON.parse(jsonPayload);
              onLogin && onLogin(user);
            }}
            onError={() => {
              alert('Login Failed');
            }}
            useOneTap
          />
        )}
      </div>
    </div>
  );
}
