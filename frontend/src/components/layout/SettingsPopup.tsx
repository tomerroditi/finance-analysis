import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsPopup({
  isOpen,
  onClose,
}: SettingsPopupProps) {
  const { t, i18n } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);
  const { isDemoMode, toggleDemoMode } = useDemoMode();

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={popupRef}
        className="w-80 bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl p-6 space-y-5 animate-in zoom-in-95 duration-200"
      >
        {/* Language Toggle */}
        <div>
          <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 block">
            {t("settings.language")}
          </label>
          <div
            className="relative flex bg-[var(--surface-light)] rounded-lg p-1 cursor-pointer select-none"
            dir="ltr"
            onClick={() => changeLanguage(i18n.language === "en" ? "he" : "en")}
          >
            {/* Sliding highlight - always uses left/right to avoid RTL flip */}
            <div
              className="absolute top-1 bottom-1 w-[calc(50%-2px)] bg-[var(--primary)] rounded-md shadow-sm transition-all duration-200"
              style={{ left: i18n.language === "en" ? "4px" : "calc(50% + 2px)" }}
            />
            <span
              className={`relative z-10 flex-1 py-1.5 text-sm font-medium text-center rounded-md transition-colors ${
                i18n.language === "en" ? "text-white" : "text-[var(--text-muted)]"
              }`}
            >
              English
            </span>
            <span
              className={`relative z-10 flex-1 py-1.5 text-sm font-medium text-center rounded-md transition-colors ${
                i18n.language === "he" ? "text-white" : "text-[var(--text-muted)]"
              }`}
            >
              עברית
            </span>
          </div>
        </div>

        {/* Demo Mode Toggle */}
        <div>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => toggleDemoMode(!isDemoMode)}
          >
            <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider cursor-pointer">
              {t("settings.demoMode")}
            </label>
            <div
              className={`w-9 h-5 rounded-full relative transition-colors ${
                isDemoMode ? "bg-amber-500" : "bg-[var(--surface-light)]"
              }`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all shadow-sm ${
                  isDemoMode
                    ? "inset-inline-start-[calc(100%-18px)]"
                    : "inset-inline-start-0.5"
                }`}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
