import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useScrollLock } from "../../hooks/useScrollLock";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
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
  Landmark,
  Sunset,
  Settings as SettingsIcon,
  Menu,
  X,
  Workflow,
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
  { path: "/liabilities", icon: Landmark, key: "liabilities" },
  { path: "/insurances", icon: Shield, key: "insurance" },
  { path: "/early-retirement", icon: Sunset, key: "earlyRetirement" },
  { path: "/data-sources", icon: Database, key: "dataSources" },
];

export function Sidebar() {
  const navigate = useNavigate();
  const { sidebarOpen, toggleSidebar, mobileSidebarOpen, setMobileSidebarOpen } = useAppStore();
  useScrollLock(mobileSidebarOpen);
  const { t, i18n } = useTranslation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const location = useLocation();

  // Auto-hide mobile top bar on scroll down, show on scroll up
  const [topBarVisible, setTopBarVisible] = useState(true);
  const lastScrollY = useRef(0);
  const handleScroll = useCallback(() => {
    const y = window.scrollY;
    if (y < 10) {
      setTopBarVisible(true);
    } else if (y > lastScrollY.current + 5) {
      setTopBarVisible(false); // scrolling down
    } else if (y < lastScrollY.current - 5) {
      setTopBarVisible(true); // scrolling up
    }
    lastScrollY.current = y;
  }, []);

  useEffect(() => {
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

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

      {/* Settings & Data Flow */}
      <div className="absolute bottom-0 inset-inline-start-0 inset-inline-end-0 p-4 border-t border-[var(--surface-light)] space-y-1">
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
        <button
          onClick={() => {
            navigate("/data-flow");
            setMobileSidebarOpen(false);
          }}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all w-full ${
            location.pathname === "/data-flow"
              ? "bg-[var(--primary)] text-white"
              : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
          }`}
        >
          <Workflow size={20} />
          {(sidebarOpen || mobileSidebarOpen) && <span className="text-sm font-medium">{t("dataFlow.title")}</span>}
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile top bar — full width, slim, auto-hides on scroll */}
      <div className={`md:hidden fixed top-0 inset-x-0 h-10 bg-[var(--surface)]/95 backdrop-blur-md border-b border-[var(--surface-light)] z-40 flex items-center justify-between px-3 transition-transform duration-200 ${topBarVisible ? "translate-y-0" : "-translate-y-full"}`}>
        <button
          onClick={() => setMobileSidebarOpen(true)}
          className="p-1.5 -ms-1.5 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
        >
          <Menu size={20} />
        </button>
        <span className="text-sm font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
          {currentPageLabel || t("sidebar.logo")}
        </span>
        <div className="w-8" />
      </div>

      {/* Desktop sidebar */}
      <aside
        className={`fixed inset-inline-start-0 top-0 h-screen bg-[var(--surface)] border-e border-[var(--surface-light)] transition-all duration-300 z-50 hidden md:block ${
          sidebarOpen ? "w-64" : "w-20"
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile sidebar overlay — full-width dropdown */}
      {mobileSidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 modal-overlay"
          onClick={() => setMobileSidebarOpen(false)}
        >
          <div
            className="fixed top-0 inset-x-0 bg-[var(--surface)] border-b border-[var(--surface-light)] animate-in slide-in-from-top duration-200 z-50 max-h-dvh overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header row */}
            <div className="h-10 flex items-center justify-between px-3 border-b border-[var(--surface-light)]">
              <span className="text-sm font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
                {t("sidebar.logo")}
              </span>
              <button
                onClick={() => setMobileSidebarOpen(false)}
                className="p-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            {/* Navigation grid */}
            <nav className="p-3 grid grid-cols-3 gap-2">
              {navItems.map((item) => {
                const badge = getBadge(item.path);
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileSidebarOpen(false)}
                    className={({ isActive }) =>
                      `relative flex flex-col items-center gap-1.5 px-2 py-3 rounded-xl transition-all text-center ${
                        isActive
                          ? "bg-[var(--primary)] text-white"
                          : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
                      }`
                    }
                  >
                    <item.icon size={20} />
                    <span className="text-[11px] font-medium leading-tight">{t(`sidebar.${item.key}`)}</span>
                    {badge != null && (
                      <span className="absolute -top-1 -end-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold px-1">
                        {badge > 99 ? "99+" : badge}
                      </span>
                    )}
                  </NavLink>
                );
              })}
              {/* Settings tile */}
              <button
                onClick={() => setSettingsOpen(!settingsOpen)}
                className={`relative flex flex-col items-center gap-1.5 px-2 py-3 rounded-xl transition-all text-center ${
                  settingsOpen
                    ? "bg-blue-500/10 text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
                }`}
              >
                <SettingsIcon size={20} />
                <span className="text-[11px] font-medium leading-tight">{t("settings.title")}</span>
              </button>
              {/* Data Flow tile */}
              <NavLink
                to="/data-flow"
                onClick={() => setMobileSidebarOpen(false)}
                className={({ isActive }) =>
                  `relative flex flex-col items-center gap-1.5 px-2 py-3 rounded-xl transition-all text-center ${
                    isActive
                      ? "bg-[var(--primary)] text-white"
                      : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
                  }`
                }
              >
                <Workflow size={20} />
                <span className="text-[11px] font-medium leading-tight">{t("dataFlow.title")}</span>
              </NavLink>
            </nav>
          </div>
        </div>
      )}

      <SettingsPopup
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </>
  );
}
