import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import type { FieldSpec, SectionSpec } from "./schema";

interface Props {
  section: SectionSpec;
  fields: Record<string, string>;
  onChange: (name: string, value: string) => void;
  onAddRow: (section: SectionSpec) => void;
  onRemoveRow: (section: SectionSpec, row: number) => void;
}

const inputClass =
  "w-full px-2.5 py-1.5 text-sm rounded-lg bg-[var(--surface)] border " +
  "border-[var(--surface-light)] text-[var(--text-primary)] " +
  "focus:outline-none focus:ring-1 focus:ring-[var(--primary)]";

function isVisible(field: FieldSpec, fields: Record<string, string>, suffix: string) {
  if (!field.visibleWhen) return true;
  const value = fields[`${field.visibleWhen.field}${suffix}`] ?? fields[field.visibleWhen.field];
  return field.visibleWhen.values.includes(value ?? "");
}

function Field({ field, name, fields, onChange }: {
  field: FieldSpec;
  name: string;
  fields: Record<string, string>;
  onChange: Props["onChange"];
}) {
  const { t } = useTranslation();
  const value = fields[name] ?? "";

  if (field.kind === "checkbox") {
    return (
      <label className="flex items-center gap-2 text-sm text-[var(--text-primary)] cursor-pointer">
        <input
          type="checkbox"
          className="shrink-0 w-3.5 h-3.5 rounded border-gray-600 text-blue-500 focus:ring-blue-500 bg-[var(--surface)] cursor-pointer"
          checked={value === "on"}
          onChange={(e) => onChange(name, e.target.checked ? "on" : "")}
        />
        {t(field.labelKey)}
      </label>
    );
  }

  return (
    <label className="block min-w-0">
      <span className="block mb-1 text-xs text-[var(--text-muted)] truncate">
        {t(field.labelKey)}
      </span>
      {field.kind === "select" ? (
        <select className={inputClass} value={value} onChange={(e) => onChange(name, e.target.value)}>
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
          ))}
        </select>
      ) : (
        <input
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
    </label>
  );
}

export function ScenarioSection({ section, fields, onChange, onAddRow, onRemoveRow }: Props) {
  const { t } = useTranslation();
  const repeatable = section.repeatable;
  const rowCount = repeatable ? Number(fields[`num_${repeatable.countKey}_fields`] ?? 0) : 0;

  return (
    <section
      className="space-y-3 p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
      data-testid={`fire-section-${section.key}`}
    >
      <div>
        <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t(section.titleKey)}
        </h3>
        {section.hintKey && (
          <p className="text-xs text-[var(--text-muted)] mt-1">{t(section.hintKey)}</p>
        )}
      </div>

      {!repeatable && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {section.fields
            .filter((field) => isVisible(field, fields, ""))
            .map((field) => (
              <Field key={field.name} field={field} name={field.name} fields={fields} onChange={onChange} />
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
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] text-[var(--text-muted)]">#{row}</span>
                <button
                  type="button"
                  aria-label={t("common.delete")}
                  className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                  onClick={() => onRemoveRow(section, row)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {section.fields
                  .filter((field) => isVisible(field, fields, String(row)))
                  .map((field) => (
                    <Field
                      key={field.name}
                      field={field}
                      name={`${field.name}${row}`}
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
