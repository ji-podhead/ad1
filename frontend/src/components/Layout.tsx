// Layout component for consistent page structure (optional, can be extended with nav/sidebar)
import * as React from 'react';
import { MainMenubar } from './ui/menubar';

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <MainMenubar />
      <main className="max-w-6xl mx-auto pt-[72px] pb-8 px-2">{children}</main>
    </div>
  );
};

export default Layout;
