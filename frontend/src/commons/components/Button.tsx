import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils';

type ButtonVariant = 'primary-solid' | 'primary-outlined' | 'neutral-outlined';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  className?: string;
  endDecorator?: ReactNode;
  fullWidth?: boolean;
  size?: ButtonSize;
  startDecorator?: ReactNode;
  variant?: ButtonVariant;
}

const variantStyles: Record<ButtonVariant, string> = {
  'primary-solid':
    'border-blue-700 bg-blue-700 text-white shadow-[0_1px_2px_rgba(15,23,42,0.12)] hover:-translate-y-px hover:border-blue-900 hover:bg-blue-900 hover:shadow-[0_8px_16px_rgba(29,78,216,0.16)] disabled:border-neutral-100 disabled:bg-neutral-100 disabled:text-neutral-400',
  'primary-outlined':
    'border-blue-200 bg-blue-50 text-blue-700 hover:border-blue-300 hover:bg-blue-100 disabled:border-neutral-200 disabled:bg-neutral-50 disabled:text-neutral-300',
  'neutral-outlined':
    'border-border bg-bg-primary text-text-primary hover:border-blue-300 hover:bg-bg-hover hover:text-blue-900 disabled:border-neutral-200 disabled:bg-neutral-50 disabled:text-neutral-300',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'min-h-[38px] gap-1.5 px-3.5 text-sm',
  md: 'min-h-[42px] gap-2 px-[18px] text-sm',
  lg: 'min-h-[46px] gap-2.5 px-[22px] text-sm',
};

export const Button = ({
  children,
  className,
  endDecorator,
  fullWidth = false,
  size = 'md',
  startDecorator,
  type = 'button',
  variant = 'primary-solid',
  ...props
}: ButtonProps) => {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-xl border font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50',
        variantStyles[variant],
        sizeStyles[size],
        fullWidth && 'w-full',
        className,
      )}
      type={type}
      {...props}
    >
      {startDecorator ? <span aria-hidden="true">{startDecorator}</span> : null}
      <span>{children}</span>
      {endDecorator ? <span aria-hidden="true">{endDecorator}</span> : null}
    </button>
  );
};
