import { useTranslation } from "react-i18next";
import type { PolicyDetails } from "../../utils/policyDetails";
import { formatDate } from "../../utils/dateFormatting";
import { formatChange, formatCurrency } from "../../utils/numberFormatting";

function fmtDate(value: string | null | undefined): string {
  return value ? formatDate(new Date(value)) : "—";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs py-1">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span className="text-white font-semibold text-end min-w-0 break-words">{children}</span>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--background)]/50 rounded-xl p-3">
      <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-1">
        {title}
      </p>
      {children}
    </div>
  );
}

/**
 * Everything the pension clearing house reports about one policy beyond its
 * balance: who runs it, what it is forecast to pay, how it did this year,
 * who may act on it, and any loan taken against it.
 */
export function PolicyDetailsSection({
  id,
  details,
  isPension,
}: {
  id: string;
  details: PolicyDetails;
  isPension: boolean;
}) {
  const { t } = useTranslation();
  const agent = details.representative;
  const loans = details.loans ?? [];

  return (
    <div id={id} data-testid="policy-details-section" className="px-4 sm:px-6 pb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
      <Block title={t("insurance.details.fund")}>
        {details.status && <Field label={t("insurance.details.status")}><span dir="auto">{details.status}</span></Field>}
        {details.manufacturer && (
          <Field label={t("insurance.details.manager")}><span dir="auto">{details.manufacturer}</span></Field>
        )}
        {details.employer && (
          <Field label={t("insurance.details.employer")}><span dir="auto">{details.employer}</span></Field>
        )}
        {details.join_date && <Field label={t("insurance.details.joined")}>{fmtDate(details.join_date)}</Field>}
      </Block>

      <Block
        title={t("insurance.details.forecastAtAge", {
          age: details.retirement_age != null ? Math.round(details.retirement_age) : "—",
        })}
      >
        {isPension ? (
          <>
            <Field label={t("insurance.details.pensionWithDeposits")}>
              {details.monthly_pension_forecast != null ? formatCurrency(details.monthly_pension_forecast) : "—"}
            </Field>
            <Field label={t("insurance.details.pensionNoDeposits")}>
              {details.monthly_pension_forecast_no_deposits != null
                ? formatCurrency(details.monthly_pension_forecast_no_deposits)
                : "—"}
            </Field>
          </>
        ) : (
          <>
            <Field label={t("insurance.details.balanceWithDeposits")}>
              {details.balance_forecast != null ? formatCurrency(details.balance_forecast) : "—"}
            </Field>
            <Field label={t("insurance.details.balanceNoDeposits")}>
              {details.balance_forecast_no_deposits != null
                ? formatCurrency(details.balance_forecast_no_deposits)
                : "—"}
            </Field>
          </>
        )}
        {details.forecast_yield_pct != null && (
          <Field label={t("insurance.details.assumedReturn")}>
            <span dir="ltr">{details.forecast_yield_pct}%</span>
          </Field>
        )}
      </Block>

      <Block title={t("insurance.details.thisYear")}>
        <Field label={t("insurance.details.ytdProfit")}>
          {details.ytd_profit != null ? (
            <span className={details.ytd_profit >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {formatChange(details.ytd_profit)}
            </span>
          ) : (
            "—"
          )}
        </Field>
        <Field label={t("insurance.details.lastMonthFee")}>
          {details.last_month_management_fee != null ? formatCurrency(details.last_month_management_fee, 2) : "—"}
        </Field>
      </Block>

      <Block title={t("insurance.details.powerOfAttorney")}>
        {agent ? (
          <>
            <Field label={t("insurance.details.agent")}>
              <span dir="auto">{agent.name ?? agent.id ?? "—"}</span>
            </Field>
            <Field label={t("insurance.details.mayAct")}>
              {agent.can_act ? t("insurance.details.yes") : t("insurance.details.no")}
            </Field>
            {agent.expires && <Field label={t("insurance.details.until")}>{fmtDate(agent.expires)}</Field>}
          </>
        ) : (
          <p className="text-xs text-[var(--text-muted)] py-1">{t("insurance.details.noAgent")}</p>
        )}
      </Block>

      <div className="sm:col-span-2">
        <Block title={t("insurance.details.loans")}>
          {loans.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] py-1">{t("insurance.details.noLoans")}</p>
          ) : (
            loans.map((loan) => (
              <div
                key={`${loan.received}-${loan.amount}`}
                data-testid="policy-loan-row"
                className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 border-b border-[var(--surface-light)]/30 last:border-0 py-1"
              >
                <Field label={t("insurance.details.loanAmount")}>{formatCurrency(loan.amount)}</Field>
                <Field label={t("insurance.details.loanBalance")}>{formatCurrency(loan.balance)}</Field>
                <Field label={t("insurance.details.loanPayment")}>{formatCurrency(loan.monthly_payment)}</Field>
                <Field label={t("insurance.details.loanEnds")}>
                  {fmtDate(loan.ends)}
                  {loan.interest_pct != null && (
                    <span className="text-[var(--text-muted)] ms-1" dir="ltr">
                      ({loan.interest_pct}%)
                    </span>
                  )}
                </Field>
              </div>
            ))
          )}
        </Block>
      </div>
    </div>
  );
}
