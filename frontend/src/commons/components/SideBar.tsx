import { useEffect, useRef, useState } from 'react';
import type React from 'react';
import { LogOut, MoreVertical, ShieldCheck } from 'lucide-react';
import { Link, NavLink, useNavigate } from 'react-router-dom';

import {
  adminSidebarMenus,
  sidebarMenus,
} from '@/commons/constants/sidebarMenus';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { cn } from '@/lib/utils';

type SideBarProps = {
  isAdminMode?: boolean;
};

const roleLabels = {
  ADMIN: '관리자',
  SUPER_ADMIN: '시스템 관리자',
  USER: '일반 사용자',
};

const roleDisplayNames = {
  ADMIN: '김태깅(마케팅)',
  SUPER_ADMIN: '허태깅(시스템 관리자)',
  USER: '이태깅(MD)',
};

export const SideBar: React.FC<SideBarProps> = ({ isAdminMode = false }) => {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN';
  const menuItems = isAdminMode ? adminSidebarMenus : sidebarMenus;
  const displayName = user ? roleDisplayNames[user.role] : '사용자';

  useEffect(() => {
    const closeUserMenu = (event: MouseEvent) => {
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', closeUserMenu);
    return () => document.removeEventListener('mousedown', closeUserMenu);
  }, []);

  const openAdminPage = () => {
    setIsUserMenuOpen(false);
    navigate('/admin');
  };

  const handleLogout = () => {
    setIsUserMenuOpen(false);
    logout();
  };

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-bg-secondary/95 backdrop-blur-[10px]">
      <div className="flex h-[52px] shrink-0 items-center border-b border-border px-[18px]">
        <Link
          className="flex items-center gap-2.5"
          to={isAdminMode ? '/admin' : '/'}
        >
          <img
            alt="ITCEN"
            className="size-7 rounded-md shadow-sm"
            src="/itcen-favicon.png"
          />
          <span>
            <span className="block text-sm font-extrabold leading-none tracking-[-0.03em] text-text-primary">
              CenTagging
            </span>
            <span className="mt-1 block text-[10px] font-medium tracking-[0.08em] text-text-quaternary">
              {isAdminMode ? 'ADMIN CONSOLE' : 'AI FURNITURE TAGGING'}
            </span>
          </span>
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        <div className="mb-3 px-2">
          <span className="text-xs font-bold text-text-secondary">
            {isAdminMode ? '관리자 기능' : '내 작업'}
          </span>
        </div>
        <nav className="flex flex-col gap-1" aria-label="주요 메뉴">
          {menuItems.map(({ Icon, id, label, to }) => (
            <NavLink
              className={({ isActive }) =>
                cn(
                  'flex min-h-10 items-center gap-2.5 rounded-md px-3 text-sm font-semibold transition-colors',
                  isActive
                    ? 'bg-blue-100 text-blue-800'
                    : 'text-text-secondary hover:bg-bg-hover hover:text-blue-900',
                )
              }
              end={
                id === 'tagging' ||
                id === 'approvals' ||
                id === 'catalog' ||
                id === 'product-submissions'
              }
              key={id}
              to={to}
            >
              <Icon size={16} strokeWidth={2.2} />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="border-t border-border px-3 py-3">
        <div className="relative" ref={userMenuRef}>
          {isUserMenuOpen ? (
            <div
              className="absolute bottom-full right-0 z-20 mb-2 w-40 overflow-hidden rounded-[4px] border border-border bg-bg-primary py-1 shadow-[var(--shadow-popup)]"
              role="menu"
            >
              {isAdmin && !isAdminMode ? (
                <button
                  className="flex h-7 w-full items-center gap-2 px-2.5 text-left text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-hover"
                  onClick={openAdminPage}
                  role="menuitem"
                  type="button"
                >
                  <ShieldCheck className="size-[13px] shrink-0" />
                  관리자 페이지
                </button>
              ) : null}
              <button
                className="flex h-7 w-full items-center gap-2 px-2.5 text-left text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-hover"
                onClick={handleLogout}
                role="menuitem"
                type="button"
              >
                <LogOut className="size-[13px] shrink-0" />
                로그아웃
              </button>
            </div>
          ) : null}
          <div className="flex items-center gap-2 rounded-[4px] bg-bg-muted/50 px-2 py-2">
            <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-white">
              <img
                alt=""
                className="size-full object-contain p-1"
                src="/itcen-favicon.png"
              />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-bold leading-[1.42] text-text-secondary">
                {displayName}
              </span>
              <span className="mt-0.5 block truncate text-[12px] leading-[18px] text-text-tertiary">
                {user ? roleLabels[user.role] : ''}
              </span>
            </span>
            <button
              aria-expanded={isUserMenuOpen}
              aria-haspopup="menu"
              aria-label="사용자 메뉴"
              className="flex size-8 shrink-0 items-center justify-center rounded-[4px] border border-transparent text-text-primary transition-colors hover:bg-bg-primary"
              onClick={() => setIsUserMenuOpen((isOpen) => !isOpen)}
              type="button"
            >
              <MoreVertical className="size-4" />
            </button>
          </div>
        </div>
        <p className="py-3 text-center text-[11px] font-semibold text-text-quaternary">
          Powered by ITCEN
        </p>
      </div>
    </aside>
  );
};
