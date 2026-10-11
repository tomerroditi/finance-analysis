import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Calculator, RefreshCw, RotateCcw, Save } from "lucide-react";
import { fireApi, type FirePlan, type FireProjection } from "../services/api";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { ScenarioSection, type TrackedLinks } from "../components/fire/ScenarioFields";
import { ProjectionResults } from "../components/fire/ProjectionResults";
import { SECTIONS, normalizeScenario, type SectionSpec } from "../components/fire/schema";
import {
  editField,
  relink,
  sourceLabels,
  syncWithTracked,
  type Draft,
} from "../components/fire/tracked";
import { ConfirmationModal } from "../components/modals/ConfirmationModal";

const secondaryButton =
  "flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] " +
  "border border-[var(--surface-light)] rounded-lg transition-colors disabled:opacity-50";

/**
 * The user's early-retirement plan.
 *
 * The form is the reverse-engineered reference calculator's, filled from
 * tracked data (`GET /api/fire/plan`): cash, investments, keren hishtalmut,
 * pension and loans each land in their own section, marked as following the
 * account they came from. Saved, the plan keeps following those accounts —
 * the dashboard card runs it — until the user types over a value.
 */
export function EarlyRetirement() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  // Null while the form shows the plan exactly as the server returned it.
  const [draft, setDraft] = useState<Draft | null>(null);
  // An unsaved calculation, shown in place of the saved plan's projection.
  const [preview, setPreview] = useState<FireProjection | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  // Always refetched on mount: the plan follows live balances, and the
  // persisted cache is written on a throttle — a reload right after Save
  // would otherwise paint (and keep) the plan from before it.
  const planQuery = useQuery({
    queryKey: qk.fire.plan(),
    queryFn: () => fireApi.getPlan().then((r) => r.data),
    staleTime: 0,
  });
  const plan = planQuery.data;

  const savedProjection = useQuery({
    queryKey: qk.fire.planProjection(),
    queryFn: () => fireApi.getPlanProjection().then((r) => r.data),
    enabled: !!plan,
  });

  const current: Draft = useMemo(
    () =>
      draft ?? {
        fields: normalizeScenario(plan?.fields ?? {}),
        linked: plan?.linked ?? [],
      },
    [draft, plan],
  );

  const update = useCallback(
    (change: (previous: Draft) => Draft) => {
      setDraft((previous) =>
        change(
          previous ?? {
            fields: normalizeScenario(plan?.fields ?? {}),
            linked: plan?.linked ?? [],
          },
        ),
      );
    },
    [plan],
  );

  const adopt = useCallback(
    (next: FirePlan) => {
      queryClient.setQueryData(qk.fire.plan(), next);
      void queryClient.invalidateQueries({ queryKey: qk.fire.planProjection() });
      setDraft(null);
      setPreview(null);
    },
    [queryClient, qk],
  );

  const calculate = useMutation({
    mutationFn: () => fireApi.calculate(current.fields).then((r) => r.data),
    onSuccess: setPreview,
  });
  const save = useMutation({
    mutationFn: () => fireApi.savePlan(current.fields, current.linked).then((r) => r.data),
    onSuccess: adopt,
  });
  const reset = useMutation({
    mutationFn: () => fireApi.resetPlan().then((r) => r.data),
    onSuccess: adopt,
  });

  const links: TrackedLinks | undefined = useMemo(() => {
    if (!plan) return undefined;
    return {
      linked: new Set(current.linked),
      scalars: plan.tracked.scalars,
      sourceLabels: sourceLabels(plan.tracked),
      onRelink: (name: string) => update((d) => relink(d, plan.tracked, name)),
    };
  }, [plan, current.linked, update]);

  const onChange = useCallback(
    (name: string, value: string) => {
      if (!plan) return;
      update((d) => editField(d, plan.tracked, name, value));
    },
    [plan, update],
  );

  const onAddRow = useCallback(
    (section: SectionSpec) => {
      const repeatable = section.repeatable;
      if (!repeatable) return;
      update((d) => {
        const countKey = `num_${repeatable.countKey}_fields`;
        const row = Number(d.fields[countKey] ?? 0) + 1;
        if (row > repeatable.max) return d;
        const fields = { ...d.fields, [countKey]: String(row) };
        for (const field of section.fields) fields[`${field.name}${row}`] = field.default;
        return { ...d, fields };
      });
    },
    [update],
  );

  const onRemoveRow = useCallback(
    (section: SectionSpec, row: number) => {
      const repeatable = section.repeatable;
      if (!repeatable) return;
      update((d) => {
        const countKey = `num_${repeatable.countKey}_fields`;
        const count = Number(d.fields[countKey] ?? 0);
        const fields = { ...d.fields };
        // Shift later rows down so the payload stays 1..n with no gaps.
        for (let index = row; index < count; index += 1) {
          for (const field of section.fields) {
            fields[`${field.name}${index}`] = d.fields[`${field.name}${index + 1}`] ?? field.default;
          }
        }
        for (const field of section.fields) delete fields[`${field.name}${count}`];
        fields[countKey] = String(Math.max(count - 1, 0));
        return { ...d, fields };
      });
    },
    [update],
  );

  const shown = preview ?? savedProjection.data ?? null;
  const busy = calculate.isPending || save.isPending || reset.isPending;

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">{t("fire.title")}</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">{t("fire.plan.subtitle")}</p>
          {(draft || (plan && !plan.saved)) && (
            <p className="text-xs text-amber-400 mt-1" data-testid="fire-plan-unsaved">
              {plan?.saved ? t("fire.plan.unsavedChanges") : t("fire.plan.notSavedYet")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            className={secondaryButton}
            disabled={!plan || busy}
            onClick={() => plan && update((d) => syncWithTracked(d, plan.tracked))}
            data-testid="fire-plan-sync"
          >
            <RefreshCw className="w-4 h-4" />
            {t("fire.plan.sync")}
          </button>
          <button
            type="button"
            className={secondaryButton}
            disabled={!plan || busy}
            onClick={() => setConfirmReset(true)}
          >
            <RotateCcw className="w-4 h-4" />
            {t("common.reset")}
          </button>
          <button
            type="button"
            className={secondaryButton}
            disabled={!plan || busy}
            onClick={() => calculate.mutate()}
            data-testid="fire-calculate"
          >
            <Calculator className="w-4 h-4" />
            {calculate.isPending ? t("fire.calculating") : t("fire.calculate")}
          </button>
          <button
            type="button"
            className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            disabled={!plan || busy}
            onClick={() => save.mutate()}
            data-testid="fire-plan-save"
          >
            <Save className="w-4 h-4" />
            {save.isPending ? t("fire.plan.saving") : t("fire.plan.save")}
          </button>
        </div>
      </div>

      {(calculate.isError || save.isError || planQuery.isError) && (
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-red-500/40">
          <p className="text-sm text-red-400">{t("fire.result.error")}</p>
        </div>
      )}

      {preview && (
        <p className="text-xs text-[var(--text-muted)]" data-testid="fire-preview-note">
          {t("fire.plan.previewNote")}
        </p>
      )}
      {shown?.status === "needs_setup" ? (
        <div
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
          data-testid="fire-needs-setup"
        >
          <p className="text-sm text-[var(--text-secondary)]">{t("fire.plan.needsSetup")}</p>
        </div>
      ) : (
        shown && <ProjectionResults projection={shown} />
      )}

      {planQuery.isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-[var(--surface)] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {SECTIONS.map((section) => (
            <ScenarioSection
              key={section.key}
              section={section}
              fields={current.fields}
              onChange={onChange}
              onAddRow={onAddRow}
              onRemoveRow={onRemoveRow}
              links={links}
            />
          ))}
        </div>
      )}

      <ConfirmationModal
        isOpen={confirmReset}
        onClose={() => setConfirmReset(false)}
        onConfirm={() => {
          setConfirmReset(false);
          reset.mutate();
        }}
        title={t("fire.plan.resetTitle")}
        message={t("fire.plan.resetMessage")}
        confirmLabel={t("common.reset")}
        isDestructive
      />
    </div>
  );
}
