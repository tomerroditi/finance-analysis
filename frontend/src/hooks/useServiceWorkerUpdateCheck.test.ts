import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

import {
  SW_UPDATE_CHECK_INTERVAL_MS,
  useServiceWorkerUpdateCheck,
} from "./useServiceWorkerUpdateCheck";

/**
 * The only thing that makes a deploy reach an already-open tab.
 *
 * vite-plugin-pwa does not poll, and the browser re-fetches `sw.js` only on
 * an in-scope navigation or after 24 h. An SPA performs neither: route
 * changes are history pushes and every `/api` call is a `fetch` the worker
 * handles. So without this hook the reload toast waits for a full page
 * load, which is why a production deploy could sit unnoticed indefinitely.
 */

type Stub = ServiceWorkerRegistration & { update: ReturnType<typeof vi.fn> };

function stubRegistration(
  overrides: Partial<ServiceWorkerRegistration> = {},
): Stub {
  return {
    installing: null,
    waiting: null,
    update: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Stub;
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

function setOnline(online: boolean) {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    get: () => online,
  });
}

describe("useServiceWorkerUpdateCheck", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setOnline(true);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible" as DocumentVisibilityState,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("asks the browser for a new worker on every interval tick", () => {
    const registration = stubRegistration();

    renderHook(() => useServiceWorkerUpdateCheck(registration));
    expect(registration.update).not.toHaveBeenCalled();

    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS * 3);

    expect(registration.update).toHaveBeenCalledTimes(3);
  });

  it("checks immediately when a backgrounded tab comes back", () => {
    const registration = stubRegistration();
    renderHook(() => useServiceWorkerUpdateCheck(registration));

    setVisibility("hidden");
    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS);
    expect(registration.update).not.toHaveBeenCalled();

    setVisibility("visible");

    expect(registration.update).toHaveBeenCalledTimes(1);
  });

  it("checks immediately when connectivity returns", () => {
    const registration = stubRegistration();
    renderHook(() => useServiceWorkerUpdateCheck(registration));

    setOnline(false);
    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS);
    expect(registration.update).not.toHaveBeenCalled();

    setOnline(true);
    window.dispatchEvent(new Event("online"));

    expect(registration.update).toHaveBeenCalledTimes(1);
  });

  it("stands down while an update is already installing or waiting", () => {
    const installing = stubRegistration({
      installing: {} as ServiceWorker,
    });
    const waiting = stubRegistration({ waiting: {} as ServiceWorker });

    renderHook(() => useServiceWorkerUpdateCheck(installing));
    renderHook(() => useServiceWorkerUpdateCheck(waiting));
    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS * 2);

    expect(installing.update).not.toHaveBeenCalled();
    expect(waiting.update).not.toHaveBeenCalled();
  });

  it("survives a rejected check so the tab keeps polling", () => {
    const registration = stubRegistration({
      update: vi.fn().mockRejectedValue(new Error("offline")),
    } as Partial<ServiceWorkerRegistration>);

    renderHook(() => useServiceWorkerUpdateCheck(registration));
    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS * 2);

    expect(registration.update).toHaveBeenCalledTimes(2);
  });

  it("tears down its timer and listeners on unmount", () => {
    const registration = stubRegistration();
    const { unmount } = renderHook(() =>
      useServiceWorkerUpdateCheck(registration),
    );

    unmount();
    vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS * 2);
    window.dispatchEvent(new Event("online"));

    expect(registration.update).not.toHaveBeenCalled();
  });

  it("does nothing before a registration exists", () => {
    expect(() => {
      renderHook(() => useServiceWorkerUpdateCheck(undefined));
      vi.advanceTimersByTime(SW_UPDATE_CHECK_INTERVAL_MS);
    }).not.toThrow();
  });
});
