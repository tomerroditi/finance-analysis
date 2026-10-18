import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useDialog } from "../context/DialogContext";

/**
 * Tells the user when retagging a purchase moved its linked refunds too.
 *
 * Listens for the `api-refunds-retagged` window event the axios response
 * interceptor dispatches after any tag write whose reply counts refunds
 * that followed the purchase to its new category and tag.
 */
export function useRefundsRetaggedToast(): void {
  const { t } = useTranslation();
  const { notifyInfo } = useDialog();

  useEffect(() => {
    const handler = (event: Event) => {
      const count = (event as CustomEvent<{ count: number }>).detail?.count ?? 0;
      if (count > 0) notifyInfo(t("transactions.refundsRetagged", { count }));
    };
    window.addEventListener("api-refunds-retagged", handler);
    return () => window.removeEventListener("api-refunds-retagged", handler);
  }, [notifyInfo, t]);
}
