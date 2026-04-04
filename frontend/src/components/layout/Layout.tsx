import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Sidebar } from "./Sidebar";
import { GlobalSearch } from "./GlobalSearch";
import { Modal } from "../common/Modal";
import { useAppStore } from "../../stores/appStore";
import { googleApi, backupApi } from "../../services/api";

export function Layout() {
  const { t } = useTranslation();
  const { sidebarOpen, searchOpen, setSearchOpen } = useAppStore();
  const [showRestorePrompt, setShowRestorePrompt] = useState(false);
  const [restoreDate, setRestoreDate] = useState("");
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [setSearchOpen]);

  useEffect(() => {
    googleApi.getPendingRestore().then((res) => {
      if (res.data.available) {
        setShowRestorePrompt(true);
        setRestoreDate(res.data.latest_backup_date ?? "");
      }
    }).catch(() => {});
  }, []);

  const handleRestore = async () => {
    setRestoring(true);
    try {
      const res = await backupApi.list();
      if (res.data.length > 0) {
        await backupApi.restore(res.data[0].filename);
        window.location.reload();
      }
    } catch {
      setRestoring(false);
    }
  };

  return (
    <div className="min-h-dvh bg-[var(--background)]">
      <Sidebar />
      <GlobalSearch isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
      <Modal
        isOpen={showRestorePrompt}
        onClose={() => setShowRestorePrompt(false)}
        title={t("settings.pendingRestoreTitle")}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6 space-y-4">
          <p className="text-sm text-[var(--text-muted)]">
            {t("settings.pendingRestoreMessage", { date: restoreDate })}
          </p>
          <div className="flex gap-3 justify-end">
            <button
              onClick={() => setShowRestorePrompt(false)}
              disabled={restoring}
              className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-light)] transition-colors disabled:opacity-50"
            >
              {t("settings.pendingRestoreSkip")}
            </button>
            <button
              onClick={handleRestore}
              disabled={restoring}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-[var(--primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {restoring ? t("settings.restoring") : t("settings.pendingRestoreConfirm")}
            </button>
          </div>
        </div>
      </Modal>
      <main
        className={`transition-all duration-300 ${
          sidebarOpen ? "md:ms-64" : "md:ms-20"
        } ms-0 pt-10 md:pt-0`}
      >
        <div className="p-2 pt-2 sm:p-4 sm:pt-4 md:p-8 md:pt-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
