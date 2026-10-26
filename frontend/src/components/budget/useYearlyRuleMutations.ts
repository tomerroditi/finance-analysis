import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { budgetApi, type YearlyAnalysis } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { yearlyRulePlan } from "./budgetPlans";

/** Patch one cached yearly analysis now and hand back how to undo it. */
async function patchYearly(
  client: ReturnType<typeof useQueryClient>,
  key: QueryKey,
  change: (rules: YearlyAnalysis["rules"]) => YearlyAnalysis["rules"],
): Promise<() => void> {
  await client.cancelQueries({ queryKey: key });
  const before = client.getQueryData<YearlyAnalysis>(key);
  if (before) client.setQueryData<YearlyAnalysis>(key, { ...before, rules: change(before.rules) });
  return () => client.setQueryData(key, before);
}

/**
 * Close/reopen and delete for a year's yearly rules, shared by the Budget
 * page's Yearly tab and the dashboard card's.
 *
 * Both answer on click — the row flips or disappears in the cached analysis
 * — and refresh along `yearlyRulePlan`: that year's tab and the Overview
 * (whose envelope list drops a closed rule) first, then what a rule can
 * reach. A failed write puts the row back.
 *
 * @param year - The year whose rules these are.
 * @param onError - Called with the failed write's kind, after the undo.
 */
export function useYearlyRuleMutations(
  year: number,
  onError: (kind: "closed" | "delete") => void,
) {
  const client = useQueryClient();
  const qk = useQueryKeys();
  const key = qk.budget.yearly(year);

  const closedMutation = useMutation({
    mutationFn: ({ id, closed }: { id: number; closed: boolean }) =>
      budgetApi.setYearlyRuleClosed(id, closed),
    onMutate: async ({ id, closed }) => ({
      refresh: yearlyRulePlan(year),
      restore: await patchYearly(client, key, (rules) =>
        rules.map((item) => (item.rule.id === id ? { ...item, closed } : item)),
      ),
    }),
    onError: (_error, _variables, context) => {
      context?.restore();
      onError("closed");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => budgetApi.deleteYearlyRule(id),
    onMutate: async (id) => ({
      refresh: yearlyRulePlan(year),
      restore: await patchYearly(client, key, (rules) =>
        rules.filter((item) => item.rule.id !== id),
      ),
    }),
    onError: (_error, _variables, context) => {
      context?.restore();
      onError("delete");
    },
  });

  return { closedMutation, deleteMutation };
}
