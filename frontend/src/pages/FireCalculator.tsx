import { useCallback, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Calculator, RotateCcw } from "lucide-react";
import { fireApi, type FireProjection } from "../services/api";
import { ScenarioSection } from "../components/fire/ScenarioFields";
import { ProjectionResults } from "../components/fire/ProjectionResults";
import { SECTIONS, initialScenario, type SectionSpec } from "../components/fire/schema";

/**
 * Standalone early-retirement calculator.
 *
 * Deliberately not wired to the user's tracked data yet: it takes a scenario
 * typed by hand and posts it to `/api/fire/calculate`, which runs the
 * reverse-engineered reference model.
 */
export function FireCalculator() {
  const { t } = useTranslation();
  const [fields, setFields] = useState<Record<string, string>>(initialScenario);
  const [projection, setProjection] = useState<FireProjection | null>(null);

  const calculate = useMutation({
    mutationFn: () => fireApi.calculate(fields).then((r) => r.data),
    onSuccess: setProjection,
  });

  const onChange = useCallback((name: string, value: string) => {
    setFields((previous) => ({ ...previous, [name]: value }));
  }, []);

  const onAddRow = useCallback((section: SectionSpec) => {
    const repeatable = section.repeatable;
    if (!repeatable) return;
    setFields((previous) => {
      const countKey = `num_${repeatable.countKey}_fields`;
      const row = Number(previous[countKey] ?? 0) + 1;
      if (row > repeatable.max) return previous;
      const next = { ...previous, [countKey]: String(row) };
      for (const field of section.fields) next[`${field.name}${row}`] = field.default;
      return next;
    });
  }, []);

  const onRemoveRow = useCallback((section: SectionSpec, row: number) => {
    const repeatable = section.repeatable;
    if (!repeatable) return;
    setFields((previous) => {
      const countKey = `num_${repeatable.countKey}_fields`;
      const count = Number(previous[countKey] ?? 0);
      const next = { ...previous };
      // Shift later rows down so the payload stays 1..n with no gaps.
      for (let index = row; index < count; index += 1) {
        for (const field of section.fields) {
          next[`${field.name}${index}`] = previous[`${field.name}${index + 1}`] ?? field.default;
        }
      }
      for (const field of section.fields) delete next[`${field.name}${count}`];
      next[countKey] = String(Math.max(count - 1, 0));
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setFields(initialScenario());
    setProjection(null);
  }, []);

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            {t("fire.title")}
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">{t("fire.subtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--surface-light)] rounded-lg transition-colors disabled:opacity-50"
          >
            <RotateCcw className="w-4 h-4" />
            {t("common.reset")}
          </button>
          <button
            type="button"
            data-testid="fire-calculate"
            disabled={calculate.isPending}
            onClick={() => calculate.mutate()}
            className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            <Calculator className="w-4 h-4" />
            {calculate.isPending ? t("fire.calculating") : t("fire.calculate")}
          </button>
        </div>
      </div>

      {calculate.isError && (
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-red-500/40">
          <p className="text-sm text-red-400">{t("fire.result.error")}</p>
        </div>
      )}

      {projection && <ProjectionResults projection={projection} />}

      <div className="space-y-4">
        {SECTIONS.map((section) => (
          <ScenarioSection
            key={section.key}
            section={section}
            fields={fields}
            onChange={onChange}
            onAddRow={onAddRow}
            onRemoveRow={onRemoveRow}
          />
        ))}
      </div>
    </div>
  );
}
