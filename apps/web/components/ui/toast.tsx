'use client';

import * as ToastPrimitive from '@radix-ui/react-toast';
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

type Tone = 'neutral' | 'success' | 'danger';
type Notify = (message: string, tone?: Tone) => void;

const ToastContext = createContext<Notify>(() => {});

interface ToastItem {
  id: number;
  message: string;
  tone: Tone;
}

let nextId = 1;

/** Radix toast provider with a tiny imperative `notify(message)` API. */
export function Toaster({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const notify = useCallback<Notify>((message, tone = 'neutral') => {
    setToasts((current) => [...current.slice(-2), { id: nextId++, message, tone }]);
  }, []);
  const remove = (id: number) => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={notify}>
      <ToastPrimitive.Provider swipeDirection="up" duration={2400}>
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            onOpenChange={(open) => !open && remove(toast.id)}
            className={cn(
              'pointer-events-auto max-w-[min(22rem,calc(100vw-2rem))] rounded-2xl border px-4 py-2.5 text-center text-sm font-semibold shadow-2xl backdrop-blur-md',
              'data-[state=open]:animate-[breathe_0.3s_ease-out_1]',
              toast.tone === 'success' && 'border-signal/40 bg-signal/15 text-signal',
              toast.tone === 'danger' && 'border-danger/40 bg-danger/15 text-danger',
              toast.tone === 'neutral' && 'border-line-strong bg-ink-raised/90 text-fg',
            )}
          >
            <ToastPrimitive.Title>{toast.message}</ToastPrimitive.Title>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="pointer-events-none fixed left-1/2 top-4 z-50 flex -translate-x-1/2 flex-col items-center gap-2 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): Notify {
  return useContext(ToastContext);
}
