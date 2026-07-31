import { create } from "zustand";
import type {
  RetirementFormValues,
  RetirementPreview,
} from "../components/retirement/RetirementGoalForm";

/**
 * Session-scoped workspace for the Early Retirement page.
 *
 * The page is a form + "what if" preview workspace, and both lived in
 * component state — so every in-app navigation unmounted the page and wiped
 * the user's edits and calculated preview, making each re-entry look like a
 * full page reload (browser-tab switches were fine: the component stayed
 * mounted). The workspace is held here so navigation away and back restores
 * exactly what the user was looking at. Deliberately NOT persisted to disk:
 * it is ephemeral working state, not saved-plan truth.
 *
 * `demo` records which mode the state belongs to — after a Demo Mode toggle
 * the stored workspace is for the other database and is dropped on read.
 */
interface RetirementWorkspaceState {
  demo: boolean | null;
  form: RetirementFormValues | null;
  hasUnsavedChanges: boolean;
  preview: RetirementPreview | null;
  saveForm: (
    demo: boolean,
    form: RetirementFormValues,
    hasUnsavedChanges: boolean,
  ) => void;
  setPreview: (demo: boolean, preview: RetirementPreview | null) => void;
  clear: () => void;
}

export const useRetirementWorkspaceStore = create<RetirementWorkspaceState>(
  (set) => ({
    demo: null,
    form: null,
    hasUnsavedChanges: false,
    preview: null,
    saveForm: (demo, form, hasUnsavedChanges) =>
      set((prev) => ({
        demo,
        form,
        hasUnsavedChanges,
        // A preview computed under the other demo mode is stale data from a
        // different database — drop it.
        preview: prev.demo === demo ? prev.preview : null,
      })),
    setPreview: (demo, preview) => set({ demo, preview }),
    clear: () =>
      set({ demo: null, form: null, hasUnsavedChanges: false, preview: null }),
  }),
);
