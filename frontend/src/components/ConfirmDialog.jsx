import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import Modal from './Modal';

const ConfirmContext = createContext(null);

/**
 * Promise-based confirmation dialog replacing window.confirm.
 * Usage: const confirm = useConfirm(); if (await confirm({ title, message, confirmLabel, danger })) { ... }
 */
export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null);
  const resolverRef = useRef(null);
  const confirmBtnRef = useRef(null);

  const confirm = useCallback((opts) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setState({
        title: opts.title || 'Are you sure?',
        message: opts.message || '',
        confirmLabel: opts.confirmLabel || 'Confirm',
        cancelLabel: opts.cancelLabel || 'Cancel',
        danger: Boolean(opts.danger),
      });
    });
  }, []);

  function settle(value) {
    resolverRef.current?.(value);
    resolverRef.current = null;
    setState(null);
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        open={Boolean(state)}
        onClose={() => settle(false)}
        title={state?.title}
        size="sm"
        initialFocusRef={confirmBtnRef}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => settle(false)}>
              {state?.cancelLabel}
            </button>
            <button
              ref={confirmBtnRef}
              type="button"
              className={state?.danger ? 'btn-base bg-danger text-ink-inverse border border-danger hover:opacity-90' : 'btn-primary'}
              onClick={() => settle(true)}
            >
              {state?.confirmLabel}
            </button>
          </>
        }
      >
        <div className="flex items-start gap-3">
          {state?.danger && <AlertTriangle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" aria-hidden="true" />}
          <p className="text-sm text-ink">{state?.message}</p>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    return async (opts) => window.confirm(opts?.message || opts?.title || 'Are you sure?');
  }
  return ctx;
}
