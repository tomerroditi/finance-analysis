import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target, BarChart3, Activity } from "lucide-react";
import {
  retirementApi,
  type RetirementSuggestions,
} from "../services/api";
import { RetirementGoalForm } from "../components/retirement/RetirementGoalForm";
import { RetirementStatus } from "../components/retirement/RetirementStatus";
import { RetirementProjections } from "../components/retirement/RetirementProjections";

type SuggestionField = keyof RetirementSuggestions;

export function EarlyRetirement() {
  const { t } = useTranslation();
  const [pendingAdjust, setPendingAdjust] = useState<{
    field: string;
    value: number;
  } | null>(null);

  const { data: goal, isLoading: goalLoading } = useQuery({
    queryKey: ["retirement", "goal"],
    queryFn: () => retirementApi.getGoal().then((r) => r.data),
  });

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["retirement", "status"],
    queryFn: () => retirementApi.getStatus().then((r) => r.data),
  });

  // Projections from saved goal (initial load only — previews overwrite this cache)
  const {
    data: projections,
    isLoading: projectionsLoading,
    isFetching: projectionsFetching,
  } = useQuery({
    queryKey: ["retirement", "projections"],
    queryFn: () => retirementApi.getProjections().then((r) => r.data),
    enabled: !!goal && goal.id !== -1,
  });

  const { data: suggestions } = useQuery({
    queryKey: ["retirement", "suggestions"],
    queryFn: () => retirementApi.getSuggestions().then((r) => r.data),
    enabled:
      !!goal &&
      goal.id !== -1 &&
      !!projections &&
      projections.readiness !== "on_track",
  });

  const handleAdjust = (field: SuggestionField, value: number) => {
    setPendingAdjust({ field, value });
  };

  const isBusy = projectionsFetching;

  return (
    <div className="flex flex-col gap-4 md:gap-6 p-4 md:p-6">
      {/* Section 1: Current Status */}
      <Section
        icon={<Activity size={18} className="text-emerald-400" />}
        title={t("earlyRetirement.sections.currentStatus")}
      >
        {statusLoading ? (
          <StatusSkeleton />
        ) : status ? (
          <RetirementStatus status={status} />
        ) : null}
      </Section>

      {/* Section 2: Retirement Goals */}
      <Section
        icon={<Target size={18} className="text-blue-400" />}
        title={t("earlyRetirement.sections.goals")}
      >
        {goalLoading ? (
          <FormSkeleton />
        ) : (
          <RetirementGoalForm
            goal={goal ?? null}
            isCalculating={isBusy}
            pendingAdjust={pendingAdjust}
            onAdjustApplied={() => setPendingAdjust(null)}
          />
        )}
      </Section>

      {/* Section 3: Projections */}
      {(!!goal || !!projections) && (
        <Section
          icon={<BarChart3 size={18} className="text-purple-400" />}
          title={t("earlyRetirement.sections.projections")}
        >
          {projectionsLoading || isBusy ? (
            <ProjectionsSkeleton />
          ) : projections ? (
            <RetirementProjections
              projections={projections}
              suggestions={suggestions}
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

function StatusSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-24 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)] animate-pulse"
        />
      ))}
    </div>
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
