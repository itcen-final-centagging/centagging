import type { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';

import { SideBar } from './SideBar';

interface LayoutProps {
  header: ReactNode;
}

export const Layout = ({ header }: LayoutProps) => {
  return (
    <div className="flex h-screen overflow-hidden font-sans">
      <SideBar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {header}
        <main className="studio-content-gradient flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
