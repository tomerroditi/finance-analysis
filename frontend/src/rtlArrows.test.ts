import { describe, it, expect } from "vitest";

/**
 * Arrow glyphs are not bidi-mirrored — only brackets are — so a bare `→` or
 * `&rarr;` in markup keeps pointing right in Hebrew. "View all →" then points
 * backwards, away from the reading direction. It shipped on six dashboard
 * links before anyone noticed. Markup arrows go through `<ForwardArrow />`,
 * which mirrors itself under RTL.
 *
 * Comments are stripped first: they are full of `a → b` prose. Translated
 * strings (locale JSON, `dataFlowContent.*.ts`) are not scanned — each
 * language picks its own arrow there.
 *
 * Source is read through `import.meta.glob` rather than `node:fs` because
 * `tsconfig.app.json` is browser-only.
 */

const SOURCES = import.meta.glob("./**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const RAW_ARROW = /→|←|&rarr;|&larr;/;

/** Blank out comments, keeping line breaks so reported line numbers hold. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

describe("RTL arrows", () => {
  it("renders horizontal arrows through ForwardArrow, never as raw glyphs", () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(SOURCES)) {
      if (/\.test\.tsx$/.test(path) || path.endsWith("/ForwardArrow.tsx")) continue;

      stripComments(source)
        .split("\n")
        .forEach((line, i) => {
          if (RAW_ARROW.test(line)) {
            offenders.push(
              `${path}:${i + 1} — a raw arrow does not mirror in RTL; use <ForwardArrow />`,
            );
          }
        });
    }

    expect(offenders).toEqual([]);
  });
});
