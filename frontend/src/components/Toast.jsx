import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from 'lucide-react';

const ToastContext = createContext(null);

const VARIANTS = {
  success: { icon: CheckCircle2, chip: 'chip-success', iconColor: 'text-success' },
  error: { icon: XCircle, chip: 'chip-danger', iconColor: 'text-danger' },
  warning: { icon: AlertTriangle, chip: 'chip-warning', iconColor: 'text-warning' },
  info: { icon: Info, chip: 'chip-info', iconColor: 'text-info' },
};

/**
 * Global toast notifications + polite live region.
 * Usage: const toast = useToast(); toast.success('Saved'); toast.error(err.message);
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (variant, message, opts = {}) => {
      const id = ++idRef.current;
      const duration = opts.duration ?? (variant === 'error' ? 8000 : 4000);
      setToasts((prev) => [...prev.slice(-4), { id, variant, message, title: opts.title }]);
      if (duration > 0) {
        setTimeout(() => dismiss(id), duration);
      }
      return id;
    },
    [dismiss]
  );

  const api = useMemo(
    () => ({
      success: (m, o) => push('success', m, o),
      error: (m, o) => push('error', m, o),
      warning: (m, o) => push('warning', m, o),
      info: (m, o) => push('info', m, o),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[min(92vw,22rem)] pointer-events-none"
      >
        {toasts.map((t) => {
          const v = VARIANTS[t.variant] || VARIANTS.info;
          const Icon = v.icon;
          return (
            <div
              key={t.id}
              role={t.variant === 'error' ? 'alert' : 'status'}
              className="pointer-events-auto bg-surface text-ink border border-border-strong rounded-lg shadow-raised p-3 flex items-start gap-3"
            >
              <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${v.iconColor}`} aria-hidden="true" />
              <div className="flex-1 min-w-0 text-sm">
                {t.title && <p className="font-semibold">{t.title}</p>}
                <p className={t.title ? 'text-ink-muted' : ''}>{t.message}</p>
              </div>
              <button type="button" onClick={() => dismiss(t.id)} className="btn-icon -m-1 p-1" aria-label="Dismiss notification">
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fail soft so components render even outside the provider (e.g. tests)
    return {
      success: () => {},
      error: (m) => console.error(m),
      warning: () => {},
      info: () => {},
      dismiss: () => {},
    };
  }
  return ctx;
}
