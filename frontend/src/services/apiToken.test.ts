import { beforeEach, describe, expect, it } from "vitest";
import { captureApiTokenFromUrl } from "./api";

describe("captureApiTokenFromUrl", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("persists the token and strips it from the URL", () => {
    window.history.replaceState(null, "", "/?apiToken=abc123");

    captureApiTokenFromUrl();

    expect(localStorage.getItem("fad_api_token")).toBe("abc123");
    expect(window.location.search).toBe("");
  });

  it("does nothing when no token parameter is present", () => {
    window.history.replaceState(null, "", "/?foo=bar");

    captureApiTokenFromUrl();

    expect(localStorage.getItem("fad_api_token")).toBeNull();
    expect(window.location.search).toBe("?foo=bar");
  });

  it("preserves unrelated query parameters", () => {
    window.history.replaceState(null, "", "/?foo=bar&apiToken=tok");

    captureApiTokenFromUrl();

    expect(localStorage.getItem("fad_api_token")).toBe("tok");
    expect(window.location.search).toBe("?foo=bar");
  });
});
