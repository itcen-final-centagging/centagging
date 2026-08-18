import type React from 'react';
import { ChevronRight, History } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { WorkflowStage } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const STEPS = [
  '이미지 업로드',
  '객체 선택',
  'SKU 선택',
  '태깅 검토',
  '저장 완료',
];

const STEP_STAGES: WorkflowStage[] = [
  'upload',
  'detect',
  'recommend',
  'review',
  'saved',
];

const getActiveStep = (stage: WorkflowStage): number => {
  if (stage === 'upload' || stage === 'analyzing') return 0;
  if (stage === 'detect' || stage === 'not-found' || stage === 'redetecting') {
    return 1;
  }
  if (stage === 'recommend' || stage === 'catalog') return 2;
  if (stage === 'review' || stage === 'saving') return 3;
  return 4;
};

export const TaggingHeader: React.FC = () => {
  const { changeStage, stage } = useTaggingWorkflow();
  const activeStep = getActiveStep(stage);

  const handleStepNavigation = (targetStage: WorkflowStage): void => {
    changeStage(targetStage);
  };

  return (
    <header className="flex h-[52px] shrink-0 items-center justify-between border-b border-border bg-bg-primary px-5">
      <span aria-hidden="true" className="w-30" />
      <ol className="hidden flex-1 items-center justify-center overflow-x-auto xl:flex">
        {STEPS.map((label, index) => {
          const isCurrent = index === activeStep;
          const isComplete = index < activeStep;
          const canNavigateBack =
            isComplete && stage !== 'saved' && stage !== 'saving';
          return (
            <li className="flex shrink-0 items-center" key={label}>
              <button
                aria-current={isCurrent ? 'step' : undefined}
                className={cn(
                  'flex items-center gap-2.5 rounded-md px-5 py-2 text-left transition-colors',
                  canNavigateBack
                    ? 'cursor-pointer hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600'
                    : 'cursor-default',
                )}
                disabled={!canNavigateBack}
                onClick={() => handleStepNavigation(STEP_STAGES[index])}
                type="button"
              >
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
              </button>
              {index < STEPS.length - 1 ? (
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
      </div>
    </header>
  );
};
