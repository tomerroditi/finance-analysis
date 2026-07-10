import type React from "react";
import type { YearlyAnalysis } from "../../services/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  year: number;
  editRule: YearlyAnalysis["rules"][number]["rule"] | null;
}

/**
 * Minimal stub — fleshed out in Task 12 (create/edit form for yearly budget
 * rules). Keeps the build green for Task 11's YearlyBudgetView, which
 * already wires up open/close state and the edit-rule payload.
 */
export const YearlyRuleModal: React.FC<Props> = () => null;
