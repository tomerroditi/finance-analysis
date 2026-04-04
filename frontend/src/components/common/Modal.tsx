import type { ReactNode } from "react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  titleId?: string;
  titleIcon?: ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl" | "3xl" | "4xl";
  children: ReactNode;
  zIndex?: "z-50" | "z-[60]";
}

const maxWidthClasses: Record<string, string> = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-lg",
  xl: "sm:max-w-xl",
  "2xl": "md:max-w-2xl",
  "3xl": "md:max-w-3xl",
  "4xl": "max-w-4xl",
};

export function Modal({
  isOpen,
  onClose,
  title,
  titleId,
  titleIcon,
  maxWidth = "md",
  children,
  zIndex = "z-50",
}: ModalProps) {
  const { t } = useTranslation();
  const generatedId = useId();
  useScrollLock(isOpen);

  if (!isOpen) return null;

  const resolvedTitleId = titleId ?? generatedId;

  return (
    <div className={`modal-overlay fixed inset-0 ${zIndex} flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200`}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={resolvedTitleId}
        className={`bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-[calc(100vw-2rem)] ${maxWidthClasses[maxWidth]} overflow-hidden animate-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col`}
      >
        <div className="px-4 md:px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/20 shrink-0">
          <h2 id={resolvedTitleId} className="text-lg md:text-xl font-bold text-white flex items-center gap-2">
            {titleIcon}
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors text-[var(--text-muted)] hover:text-white"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
