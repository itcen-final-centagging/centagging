import type React from 'react';
import { Outlet } from 'react-router-dom';

import { Header } from './Header';
import { SideBar } from './SideBar';

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen overflow-hidden font-sans">
      <SideBar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header />
        <main className="studio-content-gradient flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
