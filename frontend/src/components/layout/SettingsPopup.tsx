import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";
import { backupApi, googleApi } from "../../services/api";

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
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [creating, setCreating] = useState(false);
  const [restoringFile, setRestoringFile] = useState<string | null>(null);
  const [googleStatus, setGoogleStatus] = useState<{
    configured: boolean;
    connected: boolean;
    email?: string;
    avatar_url?: string;
  }>({ configured: false, connected: false });
  const [googleLoading, setGoogleLoading] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [setupClientId, setSetupClientId] = useState("");
  const [setupClientSecret, setSetupClientSecret] = useState("");

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
      googleApi.getStatus().then((res) => setGoogleStatus(res.data)).catch(() => {});
    }
  }, [isOpen]);

  const fetchGoogleStatus = () => {
    googleApi.getStatus().then((res) => setGoogleStatus(res.data)).catch(() => {});
  };

  const handleConnectGoogle = async () => {
    setGoogleLoading(true);
    try {
      const res = await googleApi.getAuthUrl();
      window.location.href = res.data.url;
    } catch {
      alert(t("settings.connectFailed"));
      setGoogleLoading(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    if (!confirm(t("settings.disconnectConfirm"))) return;
    setGoogleLoading(true);
    try {
      await googleApi.disconnect();
      fetchGoogleStatus();
    } catch {
      // silently fail
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSaveSetup = async () => {
    if (!setupClientId.trim() || !setupClientSecret.trim()) return;
    setGoogleLoading(true);
    try {
      await googleApi.setup(setupClientId.trim(), setupClientSecret.trim());
      setSetupClientId("");
      setSetupClientSecret("");
      setShowSetup(false);
      // Auto-trigger Google OAuth connect after saving credentials
      const res = await googleApi.getAuthUrl();
      window.location.href = res.data.url;
    } catch {
      alert(t("settings.setupFailed"));
      setGoogleLoading(false);
    }
  };

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
      alert(t("settings.backupFailed"));
    } finally {
      setCreating(false);
    }
  };

  const handleRestore = async (filename: string) => {
    if (!confirm(t("settings.restoreConfirm"))) return;
    setRestoringFile(filename);
    try {
      await backupApi.restore(filename);
      alert(t("settings.backupRestored"));
      window.location.reload();
    } catch {
      alert(t("settings.restoreFailed"));
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

        {/* Google Account */}
        <div>
          <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 block">
            {t("settings.googleAccount")}
          </label>
          {googleStatus.connected ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-[var(--surface-light)]/50">
                {googleStatus.avatar_url && (
                  <img
                    src={googleStatus.avatar_url}
                    alt=""
                    className="w-7 h-7 rounded-full shrink-0"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-[var(--text)] truncate" dir="ltr">
                    {t("settings.connectedAs", { email: googleStatus.email })}
                  </div>
                  <div className="text-[10px] text-emerald-400 font-medium flex items-center gap-1 mt-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                    {t("settings.cloudBackupActive")}
                  </div>
                </div>
                <button
                  onClick={handleDisconnectGoogle}
                  disabled={googleLoading}
                  className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-md bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                >
                  {t("settings.disconnectGoogle")}
                </button>
              </div>
              <p className="text-[10px] text-[var(--text-muted)] px-1">
                {t("settings.cloudBackupDescription")}
              </p>
            </div>
          ) : googleStatus.configured && !showSetup ? (
            <button
              onClick={handleConnectGoogle}
              disabled={googleLoading}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white text-gray-700 font-medium text-sm hover:bg-gray-50 transition-colors shadow-sm border border-gray-200 disabled:opacity-50"
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
              </svg>
              {googleLoading ? t("settings.connecting") : t("settings.connectGoogle")}
            </button>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-[var(--text-muted)]">
                {t("settings.setupDescription")}
              </p>
              <ol className="text-xs text-[var(--text-muted)] space-y-1 ps-4 list-decimal">
                <li>
                  <a
                    href="https://console.cloud.google.com/apis/credentials"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--primary)] hover:underline"
                  >
                    {t("settings.setupStep1")}
                  </a>
                </li>
                <li>{t("settings.setupStep2")}</li>
                <li>{t("settings.setupStep3")}</li>
                <li>{t("settings.setupStep4")}</li>
              </ol>
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder={t("settings.clientIdPlaceholder")}
                  value={setupClientId}
                  onChange={(e) => setSetupClientId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--surface-light)] text-[var(--text)] text-xs border border-[var(--surface-light)] focus:border-[var(--primary)] focus:outline-none"
                  dir="ltr"
                />
                <input
                  type="password"
                  placeholder={t("settings.clientSecretPlaceholder")}
                  value={setupClientSecret}
                  onChange={(e) => setSetupClientSecret(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--surface-light)] text-[var(--text)] text-xs border border-[var(--surface-light)] focus:border-[var(--primary)] focus:outline-none"
                  dir="ltr"
                />
              </div>
              <div className="flex gap-2">
                {googleStatus.configured && (
                  <button
                    onClick={() => setShowSetup(false)}
                    className="flex-1 text-xs font-medium px-3 py-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                  >
                    {t("common.cancel")}
                  </button>
                )}
                <button
                  onClick={handleSaveSetup}
                  disabled={googleLoading || !setupClientId.trim() || !setupClientSecret.trim()}
                  className="flex-1 text-xs font-medium px-3 py-2 rounded-lg bg-[var(--primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {googleLoading ? t("settings.connecting") : t("settings.setupSave")}
                </button>
              </div>
            </div>
          )}
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
