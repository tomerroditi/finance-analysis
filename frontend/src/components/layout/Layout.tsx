import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { useAppStore } from "../../stores/appStore";

export function Layout() {
  const { sidebarOpen } = useAppStore();
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="min-h-dvh bg-[var(--background)]">
      <Sidebar />
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
