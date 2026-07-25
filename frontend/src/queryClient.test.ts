import { describe, expect, it } from "vitest";
import type { Query } from "@tanstack/react-query";

import { PERSIST_BUSTER, shouldDehydrateQuery } from "./queryClient";
import { makeQueryKeys } from "./services/queryKeys";

/** Minimal stand-in for a settled query — only the two fields the predicate reads. */
function query(queryKey: readonly unknown[], status = "success"): Query {
  return { queryKey, state: { status } } as unknown as Query;
}

const qk = makeQueryKeys(false);

describe("shouldDehydrateQuery", () => {
  it("persists ordinary, non-sensitive server data", () => {
    expect(shouldDehydrateQuery(query(qk.analytics.overview()))).toBe(true);
    expect(shouldDehydrateQuery(query(qk.transactions.list("all", false)))).toBe(
      true,
    );
    expect(shouldDehydrateQuery(query(qk.retirement.projections()))).toBe(true);
  });

  it("never persists a query that has not settled successfully", () => {
    expect(shouldDehydrateQuery(query(qk.analytics.overview(), "pending"))).toBe(
      false,
    );
    expect(shouldDehydrateQuery(query(qk.analytics.overview(), "error"))).toBe(
      false,
    );
  });

  it.each([
    ["scraping state", qk.scraping.lastScrapes()],
    ["credential metadata", qk.credentials.accounts()],
    ["credential providers", qk.credentials.providers()],
    ["backup listing", qk.backups.list()],
    ["read-only rule preview", qk.tagging.rulePreview({ field: "desc" })],
  ])("excludes %s from the on-disk cache", (_label, key) => {
    expect(shouldDehydrateQuery(query(key))).toBe(false);
  });

  it("excludes the literal-key queries that live outside the factory", () => {
    for (const key of [["onboardingStatus"], ["updateCheck"], ["versionInfo"]]) {
      expect(shouldDehydrateQuery(query(key))).toBe(false);
    }
  });
});

describe("PERSIST_BUSTER", () => {
  // `PendingRefund` (links / total_refunded / remaining) and `Liability`
  // (current_rate / rate_spread / new loan_type values) changed shape after
  // the v3 bump; a hydrated v3 snapshot would feed the new components the
  // old shape. Bump this string whenever a cached response shape changes.
  it("is past v3, the last shape-incompatible cache generation", () => {
    expect(PERSIST_BUSTER).not.toBe("v3");
    expect(PERSIST_BUSTER).toBe("v4");
  });
});
