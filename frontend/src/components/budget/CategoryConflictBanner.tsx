import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, X } from "lucide-react";
import { budgetApi, type CategoryConflict } from "../../services/api";

/** Warns when a category is used by both a project and a monthly/yearly budget. */
export const CategoryConflictBanner: React.FC = () => {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(false);
  const { data } = useQuery({
    queryKey: ["categoryConflicts"],
    queryFn: () =>
      budgetApi.getCategoryConflicts().then((r) => r.data.conflicts as CategoryConflict[]),
  });

  if (dismissed || !data || data.length === 0) return null;
  const names = data.map((c) => c.category).join(", ");

  return (
    <div className="mb-4 flex gap-2.5 items-start bg-amber-500/10 border border-amber-500/40 rounded-xl px-3.5 py-3 text-sm">
      <AlertTriangle size={16} className="text-amber-400 mt-0.5 shrink-0" />
      <div dir="auto">{t("budget.categoryConflict.banner", { names })}</div>
      <button
        onClick={() => setDismissed(true)}
        aria-label={t("common.dismiss")}
        className="ms-auto text-[var(--text-muted)] hover:text-[var(--text-default)]"
      >
        <X size={16} />
      </button>
    </div>
  );
};
