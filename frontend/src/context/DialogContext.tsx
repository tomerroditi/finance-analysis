import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
} from "lucide-react";
import { useScrollLock } from "../hooks/useScrollLock";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
}

export type NotifyVariant = "success" | "error" | "warning" | "info";

export interface NotifyOptions {
  title?: string;
  message: string;
  variant?: NotifyVariant;
  duration?: number;
}

interface NotificationItem extends Required<Omit<NotifyOptions, "title">> {
  id: number;
  title?: string;
}

interface DialogContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  notify: (options: NotifyOptions) => void;
  notifySuccess: (message: string, title?: string) => void;
  notifyError: (message: string, title?: string) => void;
  notifyWarning: (message: string, title?: string) => void;
  notifyInfo: (message: string, title?: string) => void;
}

const DialogContext = createContext<DialogContextValue | undefined>(undefined);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface PendingConfirm {
  options: ConfirmOptions;
  resolve: (value: boolean) => void;
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const [confirmState, setConfirmState] = useState<PendingConfirm | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const idRef = useRef(0);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setConfirmState({ options, resolve });
    });
  }, []);

  const handleConfirmClose = useCallback(
    (result: boolean) => {
      if (confirmState) {
        confirmState.resolve(result);
        setConfirmState(null);
      }
    },
    [confirmState],
  );

  const dismissNotification = useCallback((id: number) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const notify = useCallback((options: NotifyOptions) => {
    const id = ++idRef.current;
    const item: NotificationItem = {
      id,
      title: options.title,
      message: options.message,
      variant: options.variant ?? "info",
      duration: options.duration ?? 4500,
    };
    setNotifications((prev) => [...prev, item]);
  }, []);

  const value = useMemo<DialogContextValue>(
    () => ({
      confirm,
      notify,
      notifySuccess: (message, title) =>
        notify({ message, title, variant: "success" }),
      notifyError: (message, title) =>
        notify({ message, title, variant: "error", duration: 6000 }),
      notifyWarning: (message, title) =>
        notify({ message, title, variant: "warning" }),
      notifyInfo: (message, title) =>
        notify({ message, title, variant: "info" }),
    }),
    [confirm, notify],
  );

  return (
    <DialogContext.Provider value={value}>
      {children}
      <ConfirmDialog state={confirmState} onClose={handleConfirmClose} />
      <NotificationStack
        notifications={notifications}
        onDismiss={dismissNotification}
      />
    </DialogContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDialog() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialog must be used within a DialogProvider");
  return ctx;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm() {
  return useDialog().confirm;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useNotify() {
  const { notify, notifySuccess, notifyError, notifyWarning, notifyInfo } =
    useDialog();
  return useMemo(
    () => ({
      notify,
      success: notifySuccess,
      error: notifyError,
      warning: notifyWarning,
      info: notifyInfo,
    }),
    [notify, notifySuccess, notifyError, notifyWarning, notifyInfo],
  );
}

// ---------------------------------------------------------------------------
// Confirm dialog
// ---------------------------------------------------------------------------

function ConfirmDialog({
  state,
  onClose,
}: {
  state: PendingConfirm | null;
  onClose: (result: boolean) => void;
}) {
  const { t } = useTranslation();
  const isOpen = state !== null;
  useScrollLock(isOpen);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose(false);
      if (e.key === "Enter") onClose(true);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  if (!state) return null;

  const { options } = state;
  const isDestructive = options.isDestructive ?? false;
  const title = options.title ?? t("common.confirmTitle");
  const confirmLabel = options.confirmLabel ?? t("common.confirm");
  const cancelLabel = options.cancelLabel ?? t("common.cancel");

  return (
    <div
      className="modal-overlay fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={() => onClose(false)}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-md overflow-hidden animate-in zoom-in-95 duration-150"
      >
        <div className="px-4 md:px-6 py-4 flex items-center justify-between border-b border-[var(--surface-light)] bg-[var(--surface-light)]/20">
          <h2 className="text-base md:text-lg font-bold text-white flex items-center gap-2">
            {isDestructive && (
              <AlertTriangle size={20} className="text-[var(--danger)]" />
            )}
            {title}
          </h2>
          <button
            onClick={() => onClose(false)}
            aria-label={t("common.close")}
            className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors text-[var(--text-muted)] hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-4 md:p-6">
          <p className="text-[var(--text)] text-sm leading-relaxed whitespace-pre-line">
            {options.message}
          </p>
        </div>

        <div className="px-4 md:px-6 py-4 flex gap-3 border-t border-[var(--surface-light)] bg-[var(--surface-base)]">
          <button
            onClick={() => onClose(false)}
            className="flex-1 px-4 py-2 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold text-[var(--text)] transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            autoFocus
            onClick={() => onClose(true)}
            className={`flex-1 px-4 py-2 rounded-xl text-sm font-semibold text-white shadow-lg transition-all ${
              isDestructive
                ? "bg-[var(--danger)] hover:brightness-110 shadow-red-500/20"
                : "bg-[var(--primary)] hover:bg-[var(--primary-dark)] shadow-[var(--primary)]/20"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notification toasts
// ---------------------------------------------------------------------------

const VARIANT_STYLES: Record<
  NotifyVariant,
  { ring: string; iconClass: string; Icon: typeof Info }
> = {
  success: {
    ring: "ring-1 ring-[var(--success)]/40 border-l-4 border-[var(--success)]",
    iconClass: "text-[var(--success)]",
    Icon: CheckCircle2,
  },
  error: {
    ring: "ring-1 ring-[var(--danger)]/40 border-l-4 border-[var(--danger)]",
    iconClass: "text-[var(--danger)]",
    Icon: XCircle,
  },
  warning: {
    ring: "ring-1 ring-[var(--warning)]/40 border-l-4 border-[var(--warning)]",
    iconClass: "text-[var(--warning)]",
    Icon: AlertTriangle,
  },
  info: {
    ring: "ring-1 ring-[var(--primary)]/40 border-l-4 border-[var(--primary)]",
    iconClass: "text-[var(--primary)]",
    Icon: Info,
  },
};

function NotificationStack({
  notifications,
  onDismiss,
}: {
  notifications: NotificationItem[];
  onDismiss: (id: number) => void;
}) {
  if (notifications.length === 0) return null;
  return (
    <div className="fixed z-[80] bottom-4 inset-x-4 sm:inset-x-auto sm:end-4 sm:bottom-4 flex flex-col gap-2 pointer-events-none sm:max-w-sm w-auto sm:w-96">
      {notifications.map((n) => (
        <NotificationToast
          key={n.id}
          notification={n}
          onDismiss={() => onDismiss(n.id)}
        />
      ))}
    </div>
  );
}

function NotificationToast({
  notification,
  onDismiss,
}: {
  notification: NotificationItem;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  const { Icon, ring, iconClass } = VARIANT_STYLES[notification.variant];

  useEffect(() => {
    if (notification.duration <= 0) return;
    const timer = setTimeout(onDismiss, notification.duration);
    return () => clearTimeout(timer);
  }, [notification.duration, onDismiss]);

  return (
    <div
      role={notification.variant === "error" ? "alert" : "status"}
      className={`pointer-events-auto bg-[var(--surface)] ${ring} rounded-xl shadow-2xl px-3 py-3 flex items-start gap-3 animate-in slide-in-from-bottom-2 fade-in duration-200`}
    >
      <Icon size={20} className={`shrink-0 mt-0.5 ${iconClass}`} />
      <div className="flex-1 min-w-0">
        {notification.title && (
          <div className="text-sm font-semibold text-white">
            {notification.title}
          </div>
        )}
        <div className="text-sm text-[var(--text)] leading-snug whitespace-pre-line break-words">
          {notification.message}
        </div>
      </div>
      <button
        onClick={onDismiss}
        aria-label={t("common.close")}
        className="p-1 -mt-1 -me-1 rounded-md text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] transition-colors shrink-0"
      >
        <X size={16} />
      </button>
    </div>
  );
}
