import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { GlobalSearch } from "./GlobalSearch";
import { useAppStore } from "../../stores/appStore";

export function Layout() {
  const { sidebarOpen, searchOpen, setSearchOpen } = useAppStore();
  const { pathname } = useLocation();

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
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="min-h-dvh bg-[var(--background)]">
      <Sidebar />
      <GlobalSearch isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
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
