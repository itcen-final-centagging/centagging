import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

interface StepProgressProps {
  activeStep: number;
}

const steps = [
  '이미지 업로드',
  '객체 선택',
  'SKU 선택',
  '태깅 검수',
  '저장 완료',
];

export const StepProgress = ({ activeStep }: StepProgressProps) => {
  return (
    <ol className="mb-8 flex w-full items-center">
      {steps.map((label, index) => {
        const step = index + 1;
        const isComplete = step < activeStep;
        const isActive = step === activeStep;

        return (
          <li
            className={cn(
              'relative flex flex-1 items-center gap-2 text-xs font-bold text-neutral-400 last:flex-none',
              (isActive || isComplete) && 'text-primary',
            )}
            key={label}
          >
            <span
              className={cn(
                'relative z-10 flex size-7 items-center justify-center rounded-full border border-neutral-200 bg-white',
                isComplete && 'border-primary-300 bg-primary-20 text-primary',
                isActive && 'border-primary bg-primary text-white',
              )}
            >
              {isComplete ? <Check size={14} strokeWidth={3} /> : step}
            </span>
            <span className="hidden whitespace-nowrap lg:inline">{label}</span>
            {step !== steps.length ? (
              <span className="absolute left-8 right-2 top-3.5 h-px bg-neutral-200" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
};
