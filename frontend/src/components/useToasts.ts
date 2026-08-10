import { useCallback, useRef, useState } from "react";

export interface Toast {
  id: number;
  message: string;
  kind: "success" | "error";
}

/**
 * Lives in its own module rather than beside ToastStack: React Fast Refresh
 * only preserves state for files that export components exclusively, so a
 * hook sharing a file with one silently degrades every edit into a full
 * remount.
 */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const notify = useCallback((message: string, kind: Toast["kind"] = "success") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3200);
  }, []);

  return { toasts, notify };
}
