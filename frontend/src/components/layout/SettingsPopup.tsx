import { useEffect, useRef, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLButtonElement | null>;
  sidebarOpen: boolean;
}

export function SettingsPopup({
  isOpen,
  onClose,
  anchorRef,
  sidebarOpen,
}: SettingsPopupProps) {
  const { t, i18n } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);
  const { isDemoMode, toggleDemoMode } = useDemoMode();

  const isRtl = i18n.language === "he";

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handleClick = (e: MouseEvent) => {
      if (
        popupRef.current &&
        !popupRef.current.contains(e.target as Node) &&
        anchorRef.current &&
        !anchorRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose, anchorRef]);

  if (!isOpen) return null;

  const anchorRect = anchorRef.current?.getBoundingClientRect();
  const bottom = anchorRect
    ? window.innerHeight - anchorRect.top + 8
    : 80;

  const positionStyle: React.CSSProperties = isRtl
    ? { bottom, right: sidebarOpen ? 260 : 76, position: "fixed" }
    : { bottom, left: sidebarOpen ? 260 : 76, position: "fixed" };

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  return (
    <div
      ref={popupRef}
      style={positionStyle}
      className="z-[60] w-72 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-2xl p-4 space-y-4 animate-in fade-in zoom-in-95 duration-200"
    >
      {/* Language Toggle */}
      <div>
        <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 block">
          {t("settings.language")}
        </label>
        <div className="flex bg-[var(--surface-light)] rounded-lg p-1">
          <button
            onClick={() => changeLanguage("en")}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
              i18n.language === "en"
                ? "bg-[var(--primary)] text-white shadow-sm"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("settings.english")}
          </button>
          <button
            onClick={() => changeLanguage("he")}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
              i18n.language === "he"
                ? "bg-[var(--primary)] text-white shadow-sm"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("settings.hebrew")}
          </button>
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
  );
}
