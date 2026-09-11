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

/**
 * localStorage key holding this browser's demo *sandbox* id.
 *
 * On the shared Vercel deployment every visitor gets a private copy of the
 * demo database, keyed by this id and sent on the `X-FAD-Demo-Session`
 * header. It is minted once per browser and never changes, so a returning
 * visitor lands back in the sandbox they left. A local backend ignores the
 * header unless it opts in (`FAD_DEMO_SESSIONS=1`).
 */
export const DEMO_SESSION_STORAGE_KEY = "fad_demo_session";

const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{16,64}$/;

function mintSessionId(): string {
  // randomUUID is secure-context only; getRandomValues covers plain-http
  // LAN access (e.g. `./start.sh remote` over an IP).
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Return this browser's sandbox id, minting and storing one on first use.
 * Returns `null` when storage is unavailable (private windows, blocked site
 * data) — the backend then serves the shared demo copy, as before.
 */
export function readOrCreateDemoSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const existing = localStorage.getItem(DEMO_SESSION_STORAGE_KEY);
    if (existing && SESSION_ID_PATTERN.test(existing)) return existing;
    const fresh = mintSessionId();
    localStorage.setItem(DEMO_SESSION_STORAGE_KEY, fresh);
    return fresh;
  } catch {
    return null;
  }
}
