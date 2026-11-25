import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

export const buttonVariants = cva(
  'relative inline-flex select-none items-center justify-center gap-2 overflow-hidden whitespace-nowrap font-semibold transition-[transform,background-color,opacity] duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45',
  {
    variants: {
      variant: {
        primary: 'bg-fg text-ink hover:bg-white',
        accent: 'bg-accent text-accent-ink hover:brightness-105',
        glass: 'border border-line bg-white/10 text-fg backdrop-blur-md hover:bg-white/16',
        ghost: 'text-fg-muted hover:bg-white/8 hover:text-fg',
      },
      size: {
        sm: 'h-9 rounded-full px-3.5 text-sm',
        md: 'h-11 rounded-full px-5 text-[15px]',
        lg: 'h-14 rounded-2xl px-6 text-base',
        icon: 'h-11 w-11 rounded-full',
      },
    },
    defaultVariants: { variant: 'glass', size: 'md' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...(asChild ? {} : { type: type ?? 'button' })}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';
