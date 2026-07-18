import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "../common/Modal";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";

export interface AnalysisData {
  schedule: Array<{
    payment_number: number;
    date: string;
    payment: number;
    principal_portion: number;
    interest_portion: number;
    remaining_balance: number;
  }>;
  transactions: Array<Record<string, unknown>>;
  actual_vs_expected: Array<{
    date: string;
    expected_payment: number;
    actual_payment: number;
    difference: number;
  }>;
  summary: {
    total_receipts: number;
    total_payments: number;
    total_interest_cost: number;
    interest_paid: number;
    interest_remaining: number;
    monthly_payment: number;
    remaining_balance: number;
    percent_paid: number;
    payments_made: number;
  };
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  analysisData: AnalysisData | undefined;
  onGenerate: () => void;
  isGenerating: boolean;
}

/** Liability analysis modal: summary KPIs + amortization / actual-vs-expected tabs. */
export function LiabilityAnalysisModal({
  isOpen,
  onClose,
  analysisData,
  onGenerate,
  isGenerating,
}: Props) {
  const { t } = useTranslation();
  const [analysisTab, setAnalysisTab] = useState<"schedule" | "actual">(
    "schedule",
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("liabilities.analysis")}
      maxWidth="4xl"
    >
      <div className="p-4 md:p-6 overflow-y-auto">
        {analysisData ? (
          <>
            {/* Summary */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.totalReceipts")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.total_receipts)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.totalPaymentsMade")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.total_payments)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.totalInterestCost")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.total_interest_cost)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.interestPaid")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.interest_paid)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.interestRemaining")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.interest_remaining)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.monthlyPayment")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.monthly_payment)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.remainingBalance")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {formatCurrency(analysisData.summary.remaining_balance)}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                  {t("liabilities.percentPaid")}
                </p>
                <p className="text-lg font-bold text-white mt-1" dir="ltr">
                  {analysisData.summary.percent_paid.toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Tabs + Generate Button */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex gap-2">
                <button
                  onClick={() => setAnalysisTab("schedule")}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${analysisTab === "schedule" ? "bg-[var(--primary)] text-white" : "bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
                >
                  {t("liabilities.amortizationSchedule")}
                </button>
                <button
                  onClick={() => setAnalysisTab("actual")}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${analysisTab === "actual" ? "bg-[var(--primary)] text-white" : "bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
                >
                  {t("liabilities.actualVsExpected")}
                </button>
              </div>
              <button
                onClick={onGenerate}
                disabled={isGenerating}
                className="px-4 py-2 rounded-lg text-sm font-bold bg-amber-600 text-white hover:bg-amber-700 transition-all disabled:opacity-50"
              >
                {isGenerating ? "..." : t("liabilities.generateMissing")}
              </button>
            </div>

            {/* Amortization Schedule Table */}
            {analysisTab === "schedule" && (
              <div className="overflow-x-auto max-h-96">
                <table className="min-w-[500px] w-full text-sm">
                  <thead className="sticky top-0 bg-[var(--surface)]">
                    <tr className="text-[9px] md:text-[10px] uppercase font-black tracking-wider text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                      <th className="py-2 text-start ps-2 whitespace-nowrap">
                        {t("liabilities.paymentNumber")}
                      </th>
                      <th className="py-2 text-start whitespace-nowrap">
                        {t("common.date")}
                      </th>
                      <th className="py-2 text-end whitespace-nowrap">
                        {t("liabilities.payment")}
                      </th>
                      <th className="py-2 text-end whitespace-nowrap">
                        {t("liabilities.principalPortion")}
                      </th>
                      <th className="py-2 text-end whitespace-nowrap">
                        {t("liabilities.interestPortion")}
                      </th>
                      <th className="py-2 text-end pe-2 whitespace-nowrap">
                        {t("liabilities.remainingBalance")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisData.schedule.map((row) => (
                      <tr
                        key={row.payment_number}
                        className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30"
                      >
                        <td className="py-2 ps-2 text-[var(--text-muted)]">
                          {row.payment_number}
                        </td>
                        <td className="py-2 whitespace-nowrap" dir="ltr">{formatDate(row.date)}</td>
                        <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                          {formatCurrency(row.payment)}
                        </td>
                        <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                          {formatCurrency(row.principal_portion)}
                        </td>
                        <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                          {formatCurrency(row.interest_portion)}
                        </td>
                        <td className="py-2 text-end pe-2 whitespace-nowrap" dir="ltr">
                          {formatCurrency(row.remaining_balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Actual vs Expected Table */}
            {analysisTab === "actual" && (
              <div className="overflow-x-auto max-h-96">
                <table className="min-w-[400px] w-full text-sm">
                  <thead className="sticky top-0 bg-[var(--surface)]">
                    <tr className="text-[9px] md:text-[10px] uppercase font-black tracking-wider text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                      <th className="py-2 text-start ps-2 whitespace-nowrap">
                        {t("common.date")}
                      </th>
                      <th className="py-2 text-end whitespace-nowrap">
                        {t("liabilities.expectedPayment")}
                      </th>
                      <th className="py-2 text-end whitespace-nowrap">
                        {t("liabilities.actualPayment")}
                      </th>
                      <th className="py-2 text-end pe-2 whitespace-nowrap">
                        {t("liabilities.difference")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisData.actual_vs_expected.map((row, i) => (
                      <tr
                        key={i}
                        className={`border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30 ${row.difference !== 0 ? (row.difference > 0 ? "bg-emerald-500/5" : "bg-rose-500/5") : ""}`}
                      >
                        <td className="py-2 ps-2" dir="ltr">{formatDate(row.date)}</td>
                        <td className="py-2 text-end" dir="ltr">
                          {formatCurrency(row.expected_payment)}
                        </td>
                        <td className="py-2 text-end" dir="ltr">
                          {formatCurrency(row.actual_payment)}
                        </td>
                        <td
                          className={`py-2 text-end pe-2 font-bold ${row.difference > 0 ? "text-emerald-400" : row.difference < 0 ? "text-rose-400" : ""}`}
                          dir="ltr"
                        >
                          {row.difference !== 0 &&
                            (row.difference > 0 ? "+" : "")}
                          {formatCurrency(row.difference)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Skeleton variant="card" className="h-20" />
              <Skeleton variant="card" className="h-20" />
              <Skeleton variant="card" className="h-20" />
            </div>
            <Skeleton variant="card" className="h-64" />
          </div>
        )}
      </div>
    </Modal>
  );
}
