import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import api from "./api";
import { DEMO_MODE_STORAGE_KEY } from "./demoMode";

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
