import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Receipt,
  Wallet,
  Tags,
  TrendingUp,
  Database,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "../../stores/appStore";
import { transactionsApi, scrapingApi } from "../../services/api";

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "Dashboard" },
  { path: "/transactions", icon: Receipt, label: "Transactions" },
  { path: "/budget", icon: Wallet, label: "Budget" },
  { path: "/categories", icon: Tags, label: "Categories" },
  { path: "/investments", icon: TrendingUp, label: "Investments" },
  { path: "/data-sources", icon: Database, label: "Data Sources" },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useAppStore();

  // Count uncategorized transactions
  const { data: allTransactions } = useQuery({
    queryKey: ["transactions", "all", false],
    queryFn: () => transactionsApi.getAll(undefined, false).then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });

  const uncategorizedCount =
    allTransactions?.filter(
      (t: any) => !t.category || t.category === "Uncategorized",
    ).length ?? 0;

  // Check for stale data sources (>7 days since last scrape)
  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes"],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });

  const staleSourceCount =
    lastScrapes?.filter((s: any) => {
      if (!s.last_scrape_date) return true;
      const daysSince =
        (Date.now() - new Date(s.last_scrape_date).getTime()) /
        (1000 * 60 * 60 * 24);
      return daysSince > 7;
    }).length ?? 0;

  const getBadge = (path: string): number | null => {
    if (path === "/transactions" && uncategorizedCount > 0)
      return uncategorizedCount;
    if (path === "/data-sources" && staleSourceCount > 0)
      return staleSourceCount;
    return null;
  };

  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-[var(--surface)] border-r border-[var(--surface-light)] transition-all duration-300 z-50 ${
        sidebarOpen ? "w-64" : "w-20"
      }`}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-[var(--surface-light)]">
        {sidebarOpen && (
          <span className="text-xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
            Finance
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
        >
          {sidebarOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="p-4 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `relative flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                isActive
                  ? "bg-[var(--primary)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white"
              }`
            }
          >
            <item.icon size={20} />
            {sidebarOpen && <span>{item.label}</span>}
            {(() => {
              const badge = getBadge(item.path);
              return badge != null ? (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold px-1">
                  {badge > 99 ? "99+" : badge}
                </span>
              ) : null;
            })()}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
