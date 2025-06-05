import * as React from "react"
import { Link, useLocation } from "react-router-dom"

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
export function MainMenubar({ user, onLogin, onLogout, onNav }: { user?: any, onLogin?: () => void, onLogout?: () => void, onNav?: (e: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => void }) {
  const pages = [
    { to: "/", label: "Ad1" },
    { to: "/inbox", label: "Inbox" },
    { to: "/documents", label: "Documents" },
    { to: "/validation", label: "Validation" },
    { to: "/tasks", label: "Tasks" },
    { to: "/audit", label: "Audit" },
    { to: "/ipam", label: "IAM" },
    { to: "/about", label: "About" },
    { to: "/chat", label: "Agent Chat" },
  ];
  return (
    <div className="flex items-center h-12 bg-white border-b shadow-sm px-4">
      <div className="flex-1 flex">
        {pages.map(page => (
          <MenubarItem key={page.to} to={page.to} onNav={onNav}>{page.label}</MenubarItem>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {user ? (
          <>
            <img src={user.picture} alt="pfp" className="w-8 h-8 rounded-full border" title={user.email} />
            <button onClick={onLogout} className="text-xs text-gray-500 hover:underline ml-2">Logout</button>
          </>
        ) : (
          <button onClick={onLogin} className="flex items-center gap-1 text-xs text-blue-600 hover:underline bg-blue-50 rounded px-2 py-1">
            <svg width="24" height="24" viewBox="0 0 48 48"><g><path fill="#4285F4" d="M43.611 20.083H42V20H24v8h11.303C33.962 32.833 29.418 36 24 36c-6.627 0-12-5.373-12-12s5.373-12 12-12c2.803 0 5.377.99 7.413 2.626l6.293-6.293C34.583 5.527 29.584 3 24 3 12.954 3 4 11.954 4 23s8.954 20 20 20c11.046 0 20-8.954 20-20 0-1.341-.138-2.651-.389-3.917z"/><path fill="#34A853" d="M6.306 14.691l6.571 4.819C14.655 16.104 19.008 13 24 13c2.803 0 5.377.99 7.413 2.626l6.293-6.293C34.583 5.527 29.584 3 24 3c-7.732 0-14.41 4.41-17.694 10.691z"/><path fill="#FBBC05" d="M24 43c5.356 0 10.207-1.843 13.994-4.994l-6.481-5.309C29.418 36 24 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45z"/><path fill="#EA4335" d="M43.611 20.083H42V20H24v8h11.303C34.62 32.254 29.418 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45c5.356 0 10.207-1.843 13.994-4.994l-6.481-5.309C29.418 36 24 36 24 36c-5.418 0-9.962-3.167-11.303-8.083l-6.571 4.819C9.59 40.59 16.268 45 24 45z"/></g></svg>
            Login
          </button>
        )}
      </div>
    </div>
  );
}
