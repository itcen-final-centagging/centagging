import type React from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link, Outlet } from 'react-router-dom';

import { SideBar } from './SideBar';

/** 관리자 모드에서만 승인 기능을 노출하는 전용 레이아웃입니다. */
export const AdminLayout: React.FC = () => {
  return (
    <div className="flex h-screen overflow-hidden font-sans">
      <SideBar isAdminMode />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[52px] shrink-0 items-center border-b border-border bg-bg-primary px-5">
          <Link
            className="inline-flex h-8 items-center gap-1.5 rounded-[4px] border border-border bg-bg-primary px-3 text-xs font-semibold text-text-secondary transition-colors hover:bg-bg-hover"
            to="/"
          >
            <ArrowLeft size={14} />
            관리자 나가기
          </Link>
        </header>
        <main className="studio-content-gradient flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
