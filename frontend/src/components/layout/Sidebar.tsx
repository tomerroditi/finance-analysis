import { useState, useMemo } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Receipt,
  Wallet,
  Tags,
  TrendingUp,
  Database,
  ChevronLeft,
  ChevronRight,
  Shield,
  Settings as SettingsIcon,
  Menu,
  X,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../stores/appStore";
import { transactionsApi, scrapingApi } from "../../services/api";
import { SettingsPopup } from "./SettingsPopup";

const navItems = [
  { path: "/", icon: LayoutDashboard, key: "dashboard" },
  { path: "/transactions", icon: Receipt, key: "transactions" },
  { path: "/budget", icon: Wallet, key: "budget" },
  { path: "/categories", icon: Tags, key: "categories" },
  { path: "/investments", icon: TrendingUp, key: "investments" },
  { path: "/insurances", icon: Shield, key: "insurance" },
  { path: "/data-sources", icon: Database, key: "dataSources" },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, mobileSidebarOpen, setMobileSidebarOpen } = useAppStore();
  const { t, i18n } = useTranslation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const location = useLocation();

  const isRtl = i18n.language === "he";

  // Count uncategorized transactions
  const { data: allTransactions } = useQuery({
    queryKey: ["transactions", "all", false],
    queryFn: () => transactionsApi.getAll(undefined, false).then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });

  const uncategorizedCount =
    allTransactions?.filter(
      (tx: { category?: string }) => !tx.category || tx.category === "Uncategorized",
    ).length ?? 0;

  // Check for stale data sources (>7 days since last scrape)
  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes"],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });

  const staleSourceCount = useMemo(() =>
    lastScrapes?.filter((s: { last_scrape_date: string | null }) => {
      if (!s.last_scrape_date) return true;
      const daysSince =
        // eslint-disable-next-line react-hooks/purity
        (Date.now() - new Date(s.last_scrape_date).getTime()) /
        (1000 * 60 * 60 * 24);
      return daysSince > 7;
    }).length ?? 0
  , [lastScrapes]);

  const getBadge = (path: string): number | null => {
    if (path === "/transactions" && uncategorizedCount > 0)
      return uncategorizedCount;
    if (path === "/data-sources" && staleSourceCount > 0)
      return staleSourceCount;
    return null;
  };

  // Find current page label for mobile header
  const currentNavItem = navItems.find((item) => item.path === location.pathname);
  const currentPageLabel = currentNavItem ? t(`sidebar.${currentNavItem.key}`) : "";

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-[var(--surface-light)]">
        {sidebarOpen && (
          <span className="text-xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
            {t("sidebar.logo")}
          </span>
        )}
        {/* Desktop collapse toggle - hidden on mobile */}
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors hidden md:block"
        >
          {sidebarOpen
            ? (isRtl ? <ChevronRight size={20} /> : <ChevronLeft size={20} />)
            : (isRtl ? <ChevronLeft size={20} /> : <ChevronRight size={20} />)}
        </button>
        {/* Mobile close button */}
        <button
          onClick={() => setMobileSidebarOpen(false)}
          className="p-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors md:hidden"
        >
          <X size={20} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="p-4 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={() => setMobileSidebarOpen(false)}
            className={({ isActive }) =>
              `relative flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                isActive
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
              }`
            }
          >
            <item.icon size={20} />
            {(sidebarOpen || mobileSidebarOpen) && <span>{t(`sidebar.${item.key}`)}</span>}
            {(() => {
              const badge = getBadge(item.path);
              return badge != null ? (
                <span className="absolute -top-1 -end-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold px-1">
                  {badge > 99 ? "99+" : badge}
                </span>
              ) : null;
            })()}
          </NavLink>
        ))}
      </nav>

      {/* Settings */}
      <div className="absolute bottom-0 inset-inline-start-0 inset-inline-end-0 p-4 border-t border-[var(--surface-light)]">
        <button
          onClick={() => setSettingsOpen(!settingsOpen)}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all w-full ${
            settingsOpen
              ? "bg-blue-500/10 text-[var(--primary)]"
              : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
          }`}
        >
          <SettingsIcon size={20} />
          {(sidebarOpen || mobileSidebarOpen) && <span className="text-sm font-medium">{t("settings.title")}</span>}
        </button>
      </div>
      <SettingsPopup
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </>
  );

  return (
    <>
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-inline-start-0 inset-inline-end-0 h-14 bg-[var(--surface)] border-b border-[var(--surface-light)] z-40 flex items-center px-4 gap-3">
        <button
          onClick={() => setMobileSidebarOpen(true)}
          className="p-2 -ms-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
        >
          <Menu size={22} />
        </button>
        <span className="text-lg font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
          {currentPageLabel || t("sidebar.logo")}
        </span>
      </div>

      {/* Desktop sidebar */}
      <aside
        className={`fixed inset-inline-start-0 top-0 h-screen bg-[var(--surface)] border-e border-[var(--surface-light)] transition-all duration-300 z-50 hidden md:block ${
          sidebarOpen ? "w-64" : "w-20"
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile sidebar overlay */}
      {mobileSidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={() => setMobileSidebarOpen(false)}
        >
          <aside
            className="fixed inset-inline-start-0 top-0 h-screen w-64 bg-[var(--surface)] border-e border-[var(--surface-light)] animate-in slide-in-from-left duration-200 z-50"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
}
