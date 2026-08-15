import type React from 'react';
import { ChevronRight, History, LogOut } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/hooks/useAuth';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import { cn } from '@/lib/utils';

const steps = [
  '이미지 업로드',
  '객체 선택',
  'SKU 선택',
  '태깅 검토',
  '저장 완료',
];

const roleLabels = {
  ADMIN: '관리자',
  SUPER_ADMIN: '최종 관리자',
  USER: '일반 사용자',
};

const getActiveStep = (stage: string): number => {
  if (stage === 'upload' || stage === 'analyzing') return 0;
  if (stage === 'detect' || stage === 'not-found' || stage === 'redetecting') {
    return 1;
  }
  if (stage === 'recommend' || stage === 'catalog') return 2;
  if (stage === 'review' || stage === 'saving') return 3;
  return 4;
};

export const Header: React.FC = () => {
  const { stage } = useTaggingWorkflow();
  const { logout, user } = useAuth();
  const activeStep = getActiveStep(stage);

  return (
    <header className="flex h-[52px] shrink-0 items-center justify-between border-b border-border bg-bg-primary px-5">
      <span aria-hidden="true" className="w-30" />
      <ol className="hidden flex-1 items-center justify-center overflow-x-auto xl:flex">
        {steps.map((label, index) => {
          const isCurrent = index === activeStep;
          const isComplete = index < activeStep;
          return (
            <li className="flex shrink-0 items-center" key={label}>
              <div className="flex items-center gap-2.5 px-5 py-2">
                <span
                  className={cn(
                    'flex size-5 items-center justify-center rounded-full px-1 text-xs font-bold text-white',
                    isCurrent || isComplete ? 'bg-blue-700' : 'bg-blue-300',
                  )}
                >
                  {index + 1}
                </span>
                <span
                  className={cn(
                    'text-sm font-semibold',
                    isCurrent || isComplete ? 'text-blue-700' : 'text-blue-300',
                  )}
                >
                  {label}
                </span>
              </div>
              {index < steps.length - 1 ? (
                <ChevronRight className="size-5 text-text-tertiary" />
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="flex items-center gap-2">
        <Link
          aria-label="검색 이력"
          className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-bg-tertiary px-3 text-xs font-semibold text-text-secondary transition-colors hover:bg-bg-primary"
          to="/history"
        >
          <History size={14} />
          <span className="hidden sm:inline">검색 이력</span>
        </Link>
        <div className="hidden text-right sm:block">
          <p className="text-xs font-semibold text-text-primary">
            {user?.userName}
          </p>
          <p className="text-[11px] text-text-tertiary">
            {user ? roleLabels[user.role] : ''}
          </p>
        </div>
        <button
          aria-label="로그아웃"
          className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-bg-primary px-3 text-xs font-semibold text-text-secondary transition-colors hover:border-blue-300 hover:bg-bg-hover"
          onClick={logout}
          type="button"
        >
          <LogOut size={14} />
          <span className="hidden md:inline">로그아웃</span>
        </button>
      </div>
    </header>
  );
};
