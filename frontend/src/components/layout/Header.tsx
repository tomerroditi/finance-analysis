import { useDemoMode } from "../../context/DemoModeContext";
import { Presentation } from "lucide-react";

export function Header() {
  const { isDemoMode, toggleDemoMode, isLoading } = useDemoMode();

  if (isLoading) return null;

  return (
    <header className="flex items-center justify-end px-8 py-4 mb-4 select-none">
      <div
        className={`flex items-center gap-3 px-4 py-2 rounded-full border transition-all cursor-pointer ${
          isDemoMode
            ? "bg-amber-500/10 border-amber-500/50 hover:bg-amber-500/20"
            : "bg-[var(--surface)] border-[var(--surface-light)] hover:bg-[var(--surface-light)]"
        }`}
        onClick={() => toggleDemoMode(!isDemoMode)}
      >
        <Presentation
          size={18}
          className={`transition-colors ${isDemoMode ? "text-amber-500" : "text-[var(--text-muted)]"}`}
        />
        <span
          className={`text-sm font-bold ${isDemoMode ? "text-amber-500" : "text-[var(--text-muted)]"}`}
        >
          Demo Mode
        </span>
        <div
          className={`w-8 h-4 rounded-full relative transition-colors ${isDemoMode ? "bg-amber-500" : "bg-[var(--surface-light)]"}`}
        >
          <div
            className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all shadow-sm ${isDemoMode ? "left-4.5" : "left-0.5"}`}
          />
        </div>
      </div>
    </header>
  );
}
