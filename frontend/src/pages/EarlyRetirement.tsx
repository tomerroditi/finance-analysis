import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target, BarChart3 } from "lucide-react";
import {
  retirementApi,
  type RetirementSuggestions,
} from "../services/api";
import { useQueryKeys } from "../hooks/useQueryKeys";
import {
  RetirementGoalForm,
  type RetirementPreview,
} from "../components/retirement/RetirementGoalForm";
import { RetirementProjections } from "../components/retirement/RetirementProjections";

type SuggestionField = keyof RetirementSuggestions;

export function EarlyRetirement() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [pendingAdjust, setPendingAdjust] = useState<{
    field: string;
    value: number;
    seq: number;
  } | null>(null);
  // Per-click id so applying the SAME suggestion twice still re-applies.
  const adjustSeq = useRef(0);
  // Unsaved "what if" results from the form's Calculate / Reset / Adjust
  // flows. Kept out of the query cache on purpose — see RetirementPreview.
  const [preview, setPreview] = useState<RetirementPreview | null>(null);

  const { data: goal, isLoading: goalLoading } = useQuery({
    queryKey: qk.retirement.goal(),
    queryFn: () => retirementApi.getGoal().then((r) => r.data),
  });

  const { data: status } = useQuery({
    queryKey: qk.retirement.status(),
    queryFn: () => retirementApi.getStatus().then((r) => r.data),
  });

  // Projections from the SAVED goal. A preview never touches this query —
  // it shadows it in `shownProjections` below and disappears on save.
  const {
    data: projections,
    isLoading: projectionsLoading,
    isFetching: projectionsFetching,
  } = useQuery({
    queryKey: qk.retirement.projections(),
    queryFn: () => retirementApi.getProjections().then((r) => r.data),
    enabled: !!goal && goal.id !== -1,
  });

  const { data: suggestions } = useQuery({
    queryKey: qk.retirement.suggestions(),
    queryFn: () => retirementApi.getSuggestions().then((r) => r.data),
    enabled:
      !!goal &&
      goal.id !== -1 &&
      !!projections &&
      projections.readiness !== "on_track",
  });

  const handleAdjust = (field: SuggestionField, value: number) => {
    adjustSeq.current += 1;
    setPendingAdjust({ field, value, seq: adjustSeq.current });
  };

  // A preview wins over the saved plan, and suppresses the loading skeleton:
  // the saved-plan query refetching in the background must never blank out
  // numbers the user just calculated.
  const shownProjections = preview?.projections ?? projections;
  const shownSuggestions = preview?.suggestions ?? suggestions;
  const isBusy = projectionsFetching && !preview;

  return (
    <div className="flex flex-col gap-4 md:gap-6 p-4 md:p-6">
      {/* Section 1: Retirement Goals (includes editable financial snapshot) */}
      <Section
        icon={<Target size={18} className="text-blue-400" />}
        title={t("earlyRetirement.sections.goals")}
      >
        {goalLoading ? (
          <FormSkeleton />
        ) : (
          <RetirementGoalForm
            goal={goal ?? null}
            status={status ?? null}
            isCalculating={isBusy}
            pendingAdjust={pendingAdjust}
            onAdjustApplied={() => setPendingAdjust(null)}
            onPreview={setPreview}
          />
        )}
      </Section>

      {/* Section 3: Projections */}
      {(!!goal || !!shownProjections) && (
        <Section
          icon={<BarChart3 size={18} className="text-purple-400" />}
          title={t("earlyRetirement.sections.projections")}
        >
          {(projectionsLoading && !preview) || isBusy ? (
            <ProjectionsSkeleton />
          ) : shownProjections ? (
            <RetirementProjections
              projections={shownProjections}
              suggestions={shownSuggestions}
              onAdjust={handleAdjust}
            />
          ) : null}
        </Section>
      )}
    </div>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function FormSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-16 rounded-lg bg-[var(--surface)] animate-pulse"
        />
      ))}
    </div>
  );
}

function ProjectionsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)] animate-pulse"
          />
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="h-96 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)] animate-pulse"
          />
        ))}
      </div>
    </div>
  );
}
