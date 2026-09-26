import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import api from "./api";
import { DEMO_MODE_STORAGE_KEY, DEMO_SESSION_STORAGE_KEY } from "./demoMode";

/**
 * The request interceptor is the only thing standing between "the user
 * picked Demo Mode" and "the backend actually reads the demo database" —
 * every route relies on this header rather than on any server-side state.
 * A regression here (interceptor removed, condition inverted, header typo)
 * would silently make every request act as real mode, or the reverse.
 */
describe("api request interceptor — X-FAD-Demo header", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("attaches X-FAD-Demo: 1 when the stored flag is set", async () => {
    localStorage.setItem(DEMO_MODE_STORAGE_KEY, "1");
    let observedHeader: string | null = null;

    server.use(
      http.get("/api/_test/echo-headers", ({ request }) => {
        observedHeader = request.headers.get("x-fad-demo");
        return HttpResponse.json({ ok: true });
      }),
    );

    await api.get("/_test/echo-headers");

    expect(observedHeader).toBe("1");
  });

  it("sends no X-FAD-Demo header when the stored flag is not set", async () => {
    let observedHeader: string | null = null;

    server.use(
      http.get("/api/_test/echo-headers", ({ request }) => {
        observedHeader = request.headers.get("x-fad-demo");
        return HttpResponse.json({ ok: true });
      }),
    );

    await api.get("/_test/echo-headers");

    expect(observedHeader).toBeNull();
  });
});

/**
 * The sandbox id is what keeps one visitor's demo edits out of another's on
 * the shared Vercel deployment. It has to be stable across requests (or the
 * visitor would get a fresh sandbox on every call) and sent even when the
 * stored Demo Mode flag is off, because the deployment forces the mode
 * server-side and never sets that flag in the browser.
 */
describe("api request interceptor — X-FAD-Demo-Session header", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  function captureSessionHeader(): { current: () => string | null } {
    let observed: string | null = null;
    server.use(
      http.get("/api/_test/echo-headers", ({ request }) => {
        observed = request.headers.get("x-fad-demo-session");
        return HttpResponse.json({ ok: true });
      }),
    );
    return { current: () => observed };
  }

  it("mints a sandbox id on first request and stores it", async () => {
    const header = captureSessionHeader();

    await api.get("/_test/echo-headers");

    const sent = header.current();
    expect(sent).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(localStorage.getItem(DEMO_SESSION_STORAGE_KEY)).toBe(sent);
  });

  it("reuses the stored sandbox id on later requests", async () => {
    localStorage.setItem(DEMO_SESSION_STORAGE_KEY, "visitor-0123456789abcdef");
    const header = captureSessionHeader();

    await api.get("/_test/echo-headers");
    await api.get("/_test/echo-headers");

    expect(header.current()).toBe("visitor-0123456789abcdef");
    expect(localStorage.getItem(DEMO_SESSION_STORAGE_KEY)).toBe(
      "visitor-0123456789abcdef",
    );
  });

  it("replaces a malformed stored id instead of sending it", async () => {
    localStorage.setItem(DEMO_SESSION_STORAGE_KEY, "../../etc/passwd");
    const header = captureSessionHeader();

    await api.get("/_test/echo-headers");

    expect(header.current()).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(header.current()).not.toBe("../../etc/passwd");
  });

  it("sends the sandbox id even when Demo Mode is not stored as on", async () => {
    const header = captureSessionHeader();

    await api.get("/_test/echo-headers");

    expect(localStorage.getItem(DEMO_MODE_STORAGE_KEY)).toBeNull();
    expect(header.current()).not.toBeNull();
  });
});
