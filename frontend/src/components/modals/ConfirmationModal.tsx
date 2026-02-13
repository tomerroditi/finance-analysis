import { useEffect, useState } from "react";
import { X, AlertTriangle } from "lucide-react";

interface ConfirmationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    isDestructive?: boolean;
}

export function ConfirmationModal({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    isDestructive = false,
}: ConfirmationModalProps) {
    const [isVisible, setIsVisible] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setIsVisible(true);
        } else {
            const timer = setTimeout(() => setIsVisible(false), 200);
            return () => clearTimeout(timer);
        }
    }, [isOpen]);

    if (!isVisible && !isOpen) return null;

    return (
        <div
            className={`fixed inset-0 z-[60] flex items-center justify-center p-4 transition-all duration-200 ${isOpen ? "bg-black/60 backdrop-blur-sm opacity-100" : "bg-black/0 opacity-0"
                }`}
        >
            <div
                className={`bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden transform transition-all duration-200 ${isOpen ? "scale-100 opacity-100" : "scale-95 opacity-0"
                    }`}
            >
                <div className="px-6 py-4 flex items-center justify-between border-b border-[var(--surface-light)] bg-[var(--surface-light)]/20">
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        {isDestructive && <AlertTriangle size={20} className="text-red-500" />}
                        {title}
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-[var(--surface-light)] rounded-lg transition-colors text-[var(--text-muted)] hover:text-white"
                    >
                        <X size={20} />
                    </button>
                </div>

                <div className="p-6">
                    <p className="text-[var(--text-default)] text-sm leading-relaxed">
                        {message}
                    </p>
                </div>

                <div className="px-6 py-4 flex gap-3 border-t border-[var(--surface-light)] bg-[var(--surface-base)]">
                    <button
                        onClick={onClose}
                        className="flex-1 px-4 py-2 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold text-[var(--text-default)] transition-colors"
                    >
                        {cancelLabel}
                    </button>
                    <button
                        onClick={() => {
                            onConfirm();
                            onClose();
                        }}
                        className={`flex-1 px-4 py-2 rounded-xl text-sm font-semibold text-white shadow-lg transition-all ${isDestructive
                                ? "bg-red-500 hover:bg-red-600 shadow-red-500/20"
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
