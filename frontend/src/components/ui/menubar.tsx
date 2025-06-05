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

export function MenubarItem({ to, children, ...props }: React.HTMLAttributes<HTMLDivElement> & { to?: string }) {
  const location = useLocation();
  const isActive = to && location.pathname === to;
  return (
    <Link to={to || "#"}>
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
export function MainMenubar() {
  const pages = [
    { to: "/", label: "Landing" },
    { to: "/inbox", label: "Inbox" },
    { to: "/documents", label: "Documents" },
    { to: "/validation", label: "Validation" },
    { to: "/tasks", label: "Tasks" },
    { to: "/audit", label: "Audit" },
    { to: "/agentchat", label: "Agent Chat" },
  ];
  return (
    <Menubar>
      {pages.map(page => (
        <MenubarItem key={page.to} to={page.to}>{page.label}</MenubarItem>
      ))}
    </Menubar>
  );
}
