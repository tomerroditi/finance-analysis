/**
 * localStorage key holding this client's Demo Mode choice.
 *
 * Demo Mode is per-client: the flag lives here and travels to the backend
 * on the `X-FAD-Demo` request header. The backend stores nothing per
 * client, so this value is the whole of the client's declaration.
 *
 * Standalone module (not part of `context/DemoModeContext.tsx`) so that
 * `services/api.ts` can read the flag without importing from the context
 * module, which itself imports `testingApi` from `services/api.ts` —
 * routing the value through here avoids a circular import between the two.
 */
export const DEMO_MODE_STORAGE_KEY = "fad_demo_mode";

/**
 * Read the stored flag. Safe in non-browser contexts and when storage
 * access throws (private windows, blocked site data).
 */
export function readStoredDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(DEMO_MODE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}
