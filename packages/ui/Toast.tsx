"use client";

import * as React from "react";

export type ToastTone = "neutral" | "success" | "danger";

type ToastItem = { id: number; message: string; tone: ToastTone };

const ToastContext = React.createContext<{ notify: (message: string, tone?: ToastTone) => void }>({
  notify: () => {},
});

let nextId = 1;

/**
 * Toast system for transient confirmations only. Validation errors and
 * clinical/financial facts must use inline Alert/ErrorState - never toast
 * alone. Toasts auto-dismiss but pause nothing; all action affordances
 * elsewhere remain the source of truth.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const notify = React.useCallback((message: string, tone: ToastTone = "neutral") => {
    const id = nextId++;
    setItems((prev) => [...prev.slice(-3), { id, message, tone }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);
  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="hos-toast-region" aria-live="polite" aria-label="Notifications">
        {items.map((t) => (
          <div key={t.id} className="hos-toast" data-tone={t.tone} role="status">
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastContext);
}
