import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Languages, Sparkles, Check, ArrowRight, Database, Wand2 } from "lucide-react";
import { useDemoMode } from "../context/DemoModeContext";

type Step = "language" | "path" | "done";
type Path = "real" | "demo";

/**
 * Three-step onboarding wizard for fresh installs:
 *   1. language — pick UI language (defaults to current i18n language)
 *   2. path     — "use my real data" → /data-sources, or "explore demo"
 *                 → flips Demo Mode on
 *   3. done     — confirmation + "go to dashboard" CTA
 *
 * Reachable directly via /onboarding. The OnboardingGate auto-routes
 * users here from `/` when the backend reports is_first_run.
 */
export function Onboarding() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { toggleDemoMode } = useDemoMode();
  const [step, setStep] = useState<Step>("language");
  const [chosenPath, setChosenPath] = useState<Path | null>(null);
  const [busy, setBusy] = useState(false);

  const handleLanguagePick = (lng: "en" | "he") => {
    i18n.changeLanguage(lng);
    setStep("path");
  };

  const handlePathPick = async (path: Path) => {
    setChosenPath(path);
    setBusy(true);
    try {
      if (path === "demo") {
        await toggleDemoMode(true);
      }
      setStep("done");
    } catch {
      setBusy(false);
    } finally {
      setBusy(false);
    }
  };

  const handleFinish = () => {
    if (chosenPath === "real") {
      navigate("/data-sources");
    } else {
      navigate("/");
    }
  };

  return (
    <div className="min-h-dvh w-full bg-[var(--background)] text-[var(--text)] flex items-center justify-center p-4 md:p-8">
      <div className="w-full max-w-xl">
        <StepIndicator current={step} />
        <div className="mt-8 bg-[var(--surface)] rounded-3xl border border-[var(--surface-light)] p-6 md:p-10 shadow-xl">
          {step === "language" && (
            <LanguageStep
              currentLang={i18n.language}
              onPick={handleLanguagePick}
            />
          )}
          {step === "path" && (
            <PathStep busy={busy} onPick={handlePathPick} />
          )}
          {step === "done" && (
            <DoneStep
              path={chosenPath}
              onFinish={handleFinish}
            />
          )}
        </div>
        <p className="mt-6 text-center text-xs text-[var(--text-muted)]">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="underline underline-offset-2 hover:text-[var(--text)]"
          >
            {t("onboarding.skipForNow")}
          </button>
        </p>
      </div>
    </div>
  );
}

function StepIndicator({ current }: { current: Step }) {
  const { t } = useTranslation();
  const steps: Step[] = ["language", "path", "done"];
  const currentIdx = steps.indexOf(current);
  return (
    <div
      role="progressbar"
      aria-label={t("onboarding.stepProgressLabel")}
      aria-valuemin={1}
      aria-valuemax={steps.length}
      aria-valuenow={currentIdx + 1}
      className="flex items-center gap-2 justify-center"
    >
      {steps.map((s, i) => (
        <div key={s} className="flex items-center gap-2">
          <div
            className={`h-2 w-8 rounded-full transition-colors ${
              i <= currentIdx ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"
            }`}
          />
        </div>
      ))}
    </div>
  );
}

function LanguageStep({
  currentLang,
  onPick,
}: {
  currentLang: string;
  onPick: (lng: "en" | "he") => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="text-center space-y-6">
      <div className="p-3 bg-[var(--surface-light)] rounded-2xl w-fit mx-auto text-[var(--primary)]">
        <Languages size={32} />
      </div>
      <div>
        <h1 className="text-2xl md:text-3xl font-bold mb-2">
          {t("onboarding.welcome")}
        </h1>
        <p className="text-[var(--text-muted)]">
          {t("onboarding.languagePrompt")}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <LanguageButton
          label="English"
          sub="English"
          active={currentLang.startsWith("en")}
          onClick={() => onPick("en")}
        />
        <LanguageButton
          label="עברית"
          sub="Hebrew"
          active={currentLang.startsWith("he")}
          onClick={() => onPick("he")}
        />
      </div>
    </div>
  );
}

function LanguageButton({
  label,
  sub,
  active,
  onClick,
}: {
  label: string;
  sub: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`p-4 rounded-2xl border text-start transition-colors ${
        active
          ? "border-[var(--primary)] bg-[var(--primary)]/10"
          : "border-[var(--surface-light)] hover:bg-[var(--surface-light)]/40"
      }`}
    >
      <div className="text-lg font-bold">{label}</div>
      <div className="text-xs text-[var(--text-muted)]">{sub}</div>
    </button>
  );
}

function PathStep({
  busy,
  onPick,
}: {
  busy: boolean;
  onPick: (path: Path) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl md:text-3xl font-bold">
          {t("onboarding.pathTitle")}
        </h1>
        <p className="text-[var(--text-muted)]">
          {t("onboarding.pathPrompt")}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3">
        <PathButton
          icon={Database}
          title={t("onboarding.realPathTitle")}
          description={t("onboarding.realPathDesc")}
          disabled={busy}
          onClick={() => onPick("real")}
        />
        <PathButton
          icon={Wand2}
          title={t("onboarding.demoPathTitle")}
          description={t("onboarding.demoPathDesc")}
          disabled={busy}
          onClick={() => onPick("demo")}
        />
      </div>
    </div>
  );
}

function PathButton({
  icon: Icon,
  title,
  description,
  disabled,
  onClick,
}: {
  icon: typeof Database;
  title: string;
  description: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="group flex items-start gap-4 p-4 md:p-5 rounded-2xl border border-[var(--surface-light)] hover:border-[var(--primary)] hover:bg-[var(--surface-light)]/40 transition-colors text-start disabled:opacity-50 disabled:cursor-wait"
    >
      <div className="p-3 bg-[var(--surface-light)] rounded-xl text-[var(--primary)] group-hover:bg-[var(--primary)]/10">
        <Icon size={22} />
      </div>
      <div className="flex-1">
        <div className="font-bold mb-1">{title}</div>
        <div className="text-sm text-[var(--text-muted)]">{description}</div>
      </div>
      <ArrowRight
        size={18}
        className="text-[var(--text-muted)] mt-3 transition-transform group-hover:translate-x-1 rtl:group-hover:-translate-x-1"
      />
    </button>
  );
}

function DoneStep({
  path,
  onFinish,
}: {
  path: Path | null;
  onFinish: () => void;
}) {
  const { t } = useTranslation();
  const isReal = path === "real";
  return (
    <div className="text-center space-y-6">
      <div className="p-3 bg-emerald-500/10 rounded-2xl w-fit mx-auto text-emerald-400">
        {isReal ? <Database size={32} /> : <Sparkles size={32} />}
      </div>
      <div>
        <h1 className="text-2xl md:text-3xl font-bold mb-2 flex items-center justify-center gap-2">
          <Check className="text-emerald-400" /> {t("onboarding.doneTitle")}
        </h1>
        <p className="text-[var(--text-muted)] max-w-sm mx-auto">
          {isReal ? t("onboarding.doneRealDesc") : t("onboarding.doneDemoDesc")}
        </p>
      </div>
      <button
        type="button"
        onClick={onFinish}
        className="px-6 py-3 rounded-xl bg-[var(--primary)] text-white font-bold hover:bg-[var(--primary)]/90 transition-colors w-full sm:w-auto"
      >
        {isReal
          ? t("onboarding.goToDataSources")
          : t("onboarding.goToDashboard")}
      </button>
    </div>
  );
}
