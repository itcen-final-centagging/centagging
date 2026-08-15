import type React from 'react';
import { MoreVertical } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';

import { sidebarMenus } from '@/commons/constants/sidebarMenus';
import { cn } from '@/lib/utils';

export const SideBar: React.FC = () => {
  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-bg-secondary/95 backdrop-blur-[10px]">
      <div className="flex h-[52px] shrink-0 items-center border-b border-border px-[18px]">
        <Link className="flex items-center gap-2.5" to="/">
          <span
            className="flex size-7 items-center justify-center rounded-md text-sm font-extrabold text-white shadow-sm"
            style={{ background: 'var(--gradient-primary)' }}
          >
            C
          </span>
          <span>
            <span className="block text-sm font-extrabold leading-none tracking-[-0.03em] text-text-primary">
              CenTagging
            </span>
            <span className="mt-1 block text-[10px] font-medium tracking-[0.08em] text-text-quaternary">
              AI FURNITURE TAGGING
            </span>
          </span>
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        <div className="mb-3 px-2">
          <span className="text-xs font-bold text-text-secondary">내 작업</span>
        </div>
        <nav className="flex flex-col gap-1" aria-label="주요 메뉴">
          {sidebarMenus.map(({ Icon, id, label, to }) => (
            <NavLink
              className={({ isActive }) =>
                cn(
                  'flex min-h-10 items-center gap-2.5 rounded-md px-3 text-sm font-semibold transition-colors',
                  isActive
                    ? 'bg-blue-100 text-blue-800'
                    : 'text-text-secondary hover:bg-bg-hover hover:text-blue-900',
                )
              }
              end={id === 'tagging'}
              key={id}
              to={to}
            >
              <Icon size={16} strokeWidth={2.2} />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="border-t border-border px-3 pt-3">
        <div className="flex items-center gap-2 rounded-md bg-bg-muted/60 px-2 py-2">
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ background: 'var(--gradient-primary)' }}
          >
            CT
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold leading-5 text-text-secondary">
              일반 사용자
            </span>
            <span className="block truncate text-xs text-text-tertiary">
              centagging@itcen.com
            </span>
          </span>
          <MoreVertical className="size-4 text-text-tertiary" />
        </div>
        <p className="py-3 text-center text-[11px] font-semibold text-text-quaternary">
          Powered by CenTagging
        </p>
      </div>
    </aside>
  );
};
