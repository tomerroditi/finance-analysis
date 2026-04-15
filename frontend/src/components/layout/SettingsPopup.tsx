import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { backupApi } from "../../services/api";

interface SettingsPopupProps {
  isOpen: boolean;
  onClose: () => void;
}

interface BackupEntry {
  filename: string;
  created_at: string;
  size_bytes: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function SettingsPopup({
  isOpen,
  onClose,
}: SettingsPopupProps) {
  const { t, i18n } = useTranslation();
  const popupRef = useRef<HTMLDivElement>(null);
  const { isDemoMode, toggleDemoMode } = useDemoMode();
  const confirm = useConfirm();
  const notify = useNotify();
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [creating, setCreating] = useState(false);
  const [restoringFile, setRestoringFile] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      backupApi.list().then((res) => setBackups(res.data));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  const handleCreateBackup = async () => {
    setCreating(true);
    try {
      await backupApi.create();
      const res = await backupApi.list();
      setBackups(res.data);
    } catch {
      notify.error(t("settings.backupFailed"));
    } finally {
      setCreating(false);
    }
  };

  const handleRestore = async (filename: string) => {
    const ok = await confirm({
      title: t("settings.restoreBackup"),
      message: t("settings.restoreConfirm"),
      confirmLabel: t("settings.restoreBackup"),
    });
    if (!ok) return;
    setRestoringFile(filename);
    try {
      await backupApi.restore(filename);
      notify.success(t("settings.backupRestored"));
      window.location.reload();
    } catch {
      notify.error(t("settings.restoreFailed"));
      setRestoringFile(null);
    }
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
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-96 bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl p-4 sm:p-6 space-y-5 animate-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto"
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

        {/* Database Backup */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              {t("settings.backup")}
            </label>
            <button
              onClick={handleCreateBackup}
              disabled={creating}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {creating ? t("settings.creatingBackup") : t("settings.createBackup")}
            </button>
          </div>

          {backups.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] text-center py-3">
              {t("settings.noBackups")}
            </p>
          ) : (
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {backups.map((b) => (
                <div
                  key={b.filename}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-[var(--surface-light)]/50 text-xs"
                >
                  <div className="min-w-0">
                    <div className="text-[var(--text)] truncate" dir="ltr">
                      {new Date(b.created_at).toLocaleString(
                        i18n.language === "he" ? "he-IL" : "en-US",
                        {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        },
                      )}
                    </div>
                    <div className="text-[var(--text-muted)]" dir="ltr">
                      {formatBytes(b.size_bytes)}
                    </div>
                  </div>
                  <button
                    onClick={() => handleRestore(b.filename)}
                    disabled={restoringFile !== null}
                    className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-md bg-[var(--surface-light)] text-[var(--text)] hover:bg-[var(--surface-light)]/80 transition-colors disabled:opacity-50"
                  >
                    {restoringFile === b.filename
                      ? t("settings.restoring")
                      : t("settings.restoreBackup")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
