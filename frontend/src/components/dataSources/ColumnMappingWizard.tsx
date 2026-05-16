import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { importedAccountsApi } from "../../services/api";
import type {
  AmountMode,
  ColumnMapping,
  DateFormat,
  SignConvention,
} from "../../types/importedAccount";
import { MappingPreviewTable } from "./MappingPreviewTable";

interface Props {
  file: File;
  initialMapping: ColumnMapping | null;
  saveLabelKey?:
    | "dataSources.import.mappingSaveButton"
    | "dataSources.import.mappingSaveOnlyButton";
  onSave: (mapping: ColumnMapping) => void;
}

const DATE_FORMATS: DateFormat[] = [
  "auto",
  "iso",
  "dd/mm/yyyy",
  "mm/dd/yyyy",
  "dd-mm-yyyy",
  "dd.mm.yyyy",
  "excel_serial",
];

const DATE_FORMAT_LABEL_KEY: Record<DateFormat, string> = {
  auto: "dataSources.import.dateFormatAuto",
  iso: "dataSources.import.dateFormatIso",
  "dd/mm/yyyy": "dataSources.import.dateFormatDdMmYyyy",
  "mm/dd/yyyy": "dataSources.import.dateFormatMmDdYyyy",
  "dd-mm-yyyy": "dataSources.import.dateFormatDdMmYyyyDash",
  "dd.mm.yyyy": "dataSources.import.dateFormatDdMmYyyyDot",
  excel_serial: "dataSources.import.dateFormatExcelSerial",
};

function emptyMapping(): ColumnMapping {
  return {
    skip_rows: 0,
    date: { column: "", format: "auto" },
    description: { column: "" },
    amount: {
      mode: "single",
      column: "",
      sign_convention: "positive_is_income",
    },
    category: { column: null },
    tag: { column: null },
    account_number: { column: null },
  };
}

/**
 * Mapping form + live preview. Pure local state — the parent decides
 * what to do with the produced mapping via `onSave`.
 */
export function ColumnMappingWizard({
  file,
  initialMapping,
  saveLabelKey = "dataSources.import.mappingSaveButton",
  onSave,
}: Props) {
  const { t } = useTranslation();
  const [mapping, setMapping] = useState<ColumnMapping>(
    initialMapping ?? emptyMapping(),
  );
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<
    Array<{ date: string; description: string; amount: number }>
  >([]);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    importedAccountsApi
      .preview(file, mapping)
      .then((resp) => {
        if (cancelled) return;
        setHeaders(resp.data.raw_headers);
        setPreviewRows(resp.data.rows);
        setPreviewError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setPreviewRows([]);
        setPreviewError(t("dataSources.import.importFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [file, mapping, t]);

  const isValid = useMemo(() => isMappingValid(mapping), [mapping]);

  return (
    <div className="space-y-4">
      {previewError && (
        <div className="text-xs text-red-400">{previewError}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Labeled label={t("dataSources.import.fieldDate")} htmlFor="map-date">
          <ColumnSelect
            id="map-date"
            value={mapping.date.column}
            headers={headers}
            onChange={(v) =>
              setMapping((m) => ({ ...m, date: { ...m.date, column: v } }))
            }
          />
        </Labeled>

        <Labeled
          label={t("dataSources.import.fieldDateFormat")}
          htmlFor="map-date-format"
        >
          <select
            id="map-date-format"
            value={mapping.date.format}
            onChange={(e) =>
              setMapping((m) => ({
                ...m,
                date: { ...m.date, format: e.target.value as DateFormat },
              }))
            }
            className={selectCls}
          >
            {DATE_FORMATS.map((f) => (
              <option key={f} value={f}>
                {t(DATE_FORMAT_LABEL_KEY[f])}
              </option>
            ))}
          </select>
        </Labeled>

        <Labeled
          label={t("dataSources.import.fieldDescription")}
          htmlFor="map-desc"
        >
          <ColumnSelect
            id="map-desc"
            value={mapping.description.column}
            headers={headers}
            onChange={(v) =>
              setMapping((m) => ({ ...m, description: { column: v } }))
            }
          />
        </Labeled>

        <Labeled label={t("dataSources.import.fieldAmountMode")} htmlFor="">
          <div className="flex gap-2 text-xs">
            {(["single", "split"] as AmountMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() =>
                  setMapping((m) => ({
                    ...m,
                    amount:
                      mode === "single"
                        ? {
                            mode: "single",
                            column: "",
                            sign_convention: "positive_is_income",
                          }
                        : { mode: "split", debit_column: "", credit_column: "" },
                  }))
                }
                className={`flex-1 px-3 py-2 rounded-lg border ${
                  mapping.amount.mode === mode
                    ? "border-[var(--primary)] bg-[var(--primary)]/10"
                    : "border-[var(--surface-light)]"
                }`}
              >
                {t(
                  mode === "single"
                    ? "dataSources.import.fieldAmountModeSingle"
                    : "dataSources.import.fieldAmountModeSplit",
                )}
              </button>
            ))}
          </div>
        </Labeled>

        {mapping.amount.mode === "single" ? (
          <>
            <Labeled
              label={t("dataSources.import.fieldAmountColumn")}
              htmlFor="map-amt"
            >
              <ColumnSelect
                id="map-amt"
                value={mapping.amount.column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "single"
                      ? { ...m, amount: { ...m.amount, column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
            <Labeled
              label={t("dataSources.import.fieldSignConvention")}
              htmlFor="map-sign"
            >
              <select
                id="map-sign"
                value={mapping.amount.sign_convention}
                onChange={(e) =>
                  setMapping((m) =>
                    m.amount.mode === "single"
                      ? {
                          ...m,
                          amount: {
                            ...m.amount,
                            sign_convention: e.target.value as SignConvention,
                          },
                        }
                      : m,
                  )
                }
                className={selectCls}
              >
                <option value="positive_is_income">
                  {t("dataSources.import.fieldSignPositiveIncome")}
                </option>
                <option value="positive_is_expense">
                  {t("dataSources.import.fieldSignPositiveExpense")}
                </option>
              </select>
            </Labeled>
          </>
        ) : (
          <>
            <Labeled
              label={t("dataSources.import.fieldDebitColumn")}
              htmlFor="map-debit"
            >
              <ColumnSelect
                id="map-debit"
                value={mapping.amount.debit_column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "split"
                      ? { ...m, amount: { ...m.amount, debit_column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
            <Labeled
              label={t("dataSources.import.fieldCreditColumn")}
              htmlFor="map-credit"
            >
              <ColumnSelect
                id="map-credit"
                value={mapping.amount.credit_column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "split"
                      ? { ...m, amount: { ...m.amount, credit_column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
          </>
        )}

        <Labeled
          label={t("dataSources.import.fieldCategoryColumn")}
          htmlFor="map-cat"
        >
          <ColumnSelect
            id="map-cat"
            value={mapping.category.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({
                ...m,
                category: { column: v || null },
              }))
            }
          />
        </Labeled>

        <Labeled
          label={t("dataSources.import.fieldTagColumn")}
          htmlFor="map-tag"
        >
          <ColumnSelect
            id="map-tag"
            value={mapping.tag.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({ ...m, tag: { column: v || null } }))
            }
          />
        </Labeled>

        <Labeled
          label={t("dataSources.import.fieldAccountNumberColumn")}
          htmlFor="map-acc"
        >
          <ColumnSelect
            id="map-acc"
            value={mapping.account_number.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({
                ...m,
                account_number: { column: v || null },
              }))
            }
          />
        </Labeled>

        <Labeled
          label={t("dataSources.import.fieldSkipRows")}
          htmlFor="map-skip"
        >
          <input
            id="map-skip"
            type="number"
            min={0}
            value={mapping.skip_rows}
            onChange={(e) =>
              setMapping((m) => ({
                ...m,
                skip_rows: Number.parseInt(e.target.value || "0", 10),
              }))
            }
            className={selectCls}
          />
        </Labeled>
      </div>

      <div>
        <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">
          {t("dataSources.import.mappingMappedPreview")}
        </h4>
        <MappingPreviewTable rows={previewRows} />
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          disabled={!isValid}
          onClick={() => onSave(mapping)}
          className="px-5 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold disabled:opacity-50"
        >
          {t(saveLabelKey)}
        </button>
      </div>
    </div>
  );
}

const selectCls =
  "w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-3 py-2 text-sm outline-none focus:border-[var(--primary)]";

function Labeled({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5"
      >
        {label}
      </label>
      {children}
    </div>
  );
}

interface ColumnSelectProps {
  id: string;
  value: string;
  headers: string[];
  allowNone?: boolean;
  onChange: (v: string) => void;
}

function ColumnSelect({
  id,
  value,
  headers,
  allowNone,
  onChange,
}: ColumnSelectProps) {
  const { t } = useTranslation();
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={selectCls}
    >
      <option value="">
        {allowNone ? t("dataSources.import.noneOption") : "—"}
      </option>
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </select>
  );
}

function isMappingValid(m: ColumnMapping): boolean {
  if (!m.date.column || !m.date.format) return false;
  if (!m.description.column) return false;
  if (m.amount.mode === "single") {
    if (!m.amount.column || !m.amount.sign_convention) return false;
  } else {
    if (!m.amount.debit_column || !m.amount.credit_column) return false;
  }
  return true;
}
