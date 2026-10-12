import { useId } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Link2, Plus, RotateCcw, Trash2 } from "lucide-react";
import { InfoTooltip } from "../common/InfoTooltip";
import {
  fieldLabelKey,
  helpKey,
  holds,
  isFieldVisible,
  type FieldSpec,
  type SectionSpec,
} from "./schema";

/** How the form ties to tracked data. Absent on a free-standing scenario. */
export interface TrackedLinks {
  /** Single-value fields following tracked data. */
  linked: Set<string>;
  /** What tracked data says each of those fields is. */
  scalars: Record<string, string>;
  /** Tracked account name by source id (`investment:12`). */
  sourceLabels: Record<string, string>;
  /** Make a field follow tracked data again. */
  onRelink: (name: string) => void;
}

interface Props {
  section: SectionSpec;
  fields: Record<string, string>;
  onChange: (name: string, value: string) => void;
  onAddRow: (section: SectionSpec) => void;
  onRemoveRow: (section: SectionSpec, row: number) => void;
  /** Swap a row with its neighbour; only reorderable sections offer it. */
  onMoveRow?: (section: SectionSpec, row: number, to: number) => void;
  links?: TrackedLinks;
}

const inputClass =
  "w-full px-2.5 py-1.5 text-sm rounded-lg bg-[var(--surface)] border " +
  "border-[var(--surface-light)] text-[var(--text-primary)] " +
  "focus:outline-none focus:ring-1 focus:ring-[var(--primary)]";

function LinkMark({ name, links }: { name: string; links?: TrackedLinks }) {
  const { t } = useTranslation();
  if (!links || !(name in links.scalars)) return null;
  if (links.linked.has(name)) {
    return (
      <span
        className="inline-flex items-center text-sky-400"
        title={t("fire.plan.linkedField")}
        data-testid={`fire-linked-${name}`}
      >
        <Link2 className="w-3 h-3" />
      </span>
    );
  }
  return (
    <button
      type="button"
      className="inline-flex items-center text-[var(--text-muted)] hover:text-sky-400 transition-colors"
      title={t("fire.plan.relinkField")}
      aria-label={t("fire.plan.relinkField")}
      data-testid={`fire-relink-${name}`}
      onClick={() => links.onRelink(name)}
    >
      <RotateCcw className="w-3 h-3" />
    </button>
  );
}

function Help({ field, name }: { field: FieldSpec; name: string }) {
  const { t } = useTranslation();
  return (
    <span className="shrink-0 inline-flex" data-testid={`fire-help-${name}`}>
      <InfoTooltip text={t(helpKey(field))} iconSize={12} width={260} />
    </span>
  );
}

/**
 * One input with its label and explanation. The label points at the input
 * rather than wrapping it, so the info button beside it is not the label's
 * control: clicking the label still focuses the input.
 */
function Field({ field, name, suffix, fields, onChange, links }: {
  field: FieldSpec;
  name: string;
  suffix: string;
  fields: Record<string, string>;
  onChange: Props["onChange"];
  links?: TrackedLinks;
}) {
  const { t } = useTranslation();
  const id = useId();
  const value = fields[name] ?? "";
  const label = t(fieldLabelKey(field, fields, suffix));

  if (field.kind === "checkbox") {
    return (
      <div className="flex items-center gap-2 min-w-0">
        <input
          id={id}
          type="checkbox"
          className="shrink-0 w-3.5 h-3.5 rounded border-gray-600 text-blue-500 focus:ring-blue-500 bg-[var(--surface)] cursor-pointer"
          checked={value === "on"}
          onChange={(e) => onChange(name, e.target.checked ? "on" : "")}
        />
        <label htmlFor={id} className="text-sm text-[var(--text-primary)] cursor-pointer">
          {label}
        </label>
        <Help field={field} name={name} />
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1 mb-1 text-xs text-[var(--text-muted)] min-w-0">
        <label htmlFor={id} className="truncate">{label}</label>
        <Help field={field} name={name} />
        <LinkMark name={name} links={links} />
      </div>
      {field.kind === "select" ? (
        <select
          id={id}
          className={inputClass}
          value={value}
          onChange={(e) => onChange(name, e.target.value)}
        >
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className={inputClass}
          type={field.kind === "number" ? "number" : field.kind}
          value={value}
          min={field.min}
          max={field.max}
          step={field.step}
          dir={field.kind === "number" ? "ltr" : undefined}
          onChange={(e) => onChange(name, e.target.value)}
        />
      )}
    </div>
  );
}

function RowSource({ source, links }: { source: string; links?: TrackedLinks }) {
  const { t } = useTranslation();
  if (!source || !links) return null;
  // The household's typical spending and income are not accounts with a name.
  const label = source.startsWith("tracked:")
    ? t(`fire.plan.source.${source.slice("tracked:".length)}`)
    : links.sourceLabels[source] ?? t("fire.plan.linkedRow");
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] text-sky-400 min-w-0"
      title={t("fire.plan.linkedRow")}
    >
      <Link2 className="shrink-0 w-3 h-3" />
      <span className="truncate" dir="auto">{label}</span>
    </span>
  );
}

function sectionHintKey(section: SectionSpec, fields: Record<string, string>): string | undefined {
  if (section.hintVariants) {
    return `${section.hintVariants.prefix}.${fields[section.hintVariants.field] ?? ""}`;
  }
  return section.hintKey;
}

const rowButtonClass =
  "shrink-0 p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors " +
  "disabled:opacity-30 disabled:hover:text-[var(--text-muted)]";

export function ScenarioSection({
  section,
  fields,
  onChange,
  onAddRow,
  onRemoveRow,
  onMoveRow,
  links,
}: Props) {
  const { t } = useTranslation();
  if (section.visibleWhen && !holds(section.visibleWhen, fields)) return null;
  const repeatable = section.repeatable;
  const rowCount = repeatable ? Number(fields[`num_${repeatable.countKey}_fields`] ?? 0) : 0;
  const hintKey = sectionHintKey(section, fields);
  const reorder = section.reorderable && onMoveRow ? onMoveRow : undefined;

  return (
    <section
      className="space-y-3 p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
      data-testid={`fire-section-${section.key}`}
    >
      <div>
        <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t(section.titleKey)}
        </h3>
        {hintKey && (
          <p className="text-xs text-[var(--text-muted)] mt-1" data-testid={`fire-hint-${section.key}`}>
            {t(hintKey)}
          </p>
        )}
      </div>

      {!repeatable && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {section.fields
            .filter((field) => field.kind !== "hidden" && isFieldVisible(field, fields))
            .map((field) => (
              <Field
                key={field.name}
                field={field}
                name={field.name}
                suffix=""
                fields={fields}
                onChange={onChange}
                links={links}
              />
            ))}
        </div>
      )}

      {repeatable && (
        <div className="space-y-3">
          {Array.from({ length: rowCount }, (_, index) => index + 1).map((row) => (
            <div
              key={row}
              className="p-3 rounded-xl bg-[var(--surface-light)] border border-[var(--surface-light)]"
              data-testid={`fire-row-${section.key}-${row}`}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="flex items-center gap-2 min-w-0 text-[10px] text-[var(--text-muted)]">
                  #{row}
                  {section.sourceField && (
                    <RowSource source={fields[`${section.sourceField}${row}`] ?? ""} links={links} />
                  )}
                </span>
                <span className="flex items-center gap-1">
                  {reorder && (
                    <>
                      <button
                        type="button"
                        aria-label={t("fire.action.moveUp")}
                        title={t("fire.action.moveUp")}
                        className={rowButtonClass}
                        disabled={row === 1}
                        data-testid={`fire-move-up-${section.key}-${row}`}
                        onClick={() => reorder(section, row, row - 1)}
                      >
                        <ChevronUp className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label={t("fire.action.moveDown")}
                        title={t("fire.action.moveDown")}
                        className={rowButtonClass}
                        disabled={row === rowCount}
                        data-testid={`fire-move-down-${section.key}-${row}`}
                        onClick={() => reorder(section, row, row + 1)}
                      >
                        <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    aria-label={t("common.delete")}
                    className={rowButtonClass}
                    data-testid={`fire-remove-${section.key}-${row}`}
                    onClick={() => onRemoveRow(section, row)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {section.fields
                  .filter((field) => field.kind !== "hidden" && isFieldVisible(field, fields, String(row)))
                  .map((field) => (
                    <Field
                      key={field.name}
                      field={field}
                      name={`${field.name}${row}`}
                      suffix={String(row)}
                      fields={fields}
                      onChange={onChange}
                    />
                  ))}
              </div>
            </div>
          ))}
          <button
            type="button"
            className="flex items-center gap-2 px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--surface-light)] rounded-lg transition-colors disabled:opacity-50"
            disabled={rowCount >= repeatable.max}
            onClick={() => onAddRow(section)}
          >
            <Plus className="w-4 h-4" />
            {t(repeatable.addLabelKey)}
          </button>
        </div>
      )}
    </section>
  );
}
