import { describe, it, expect } from "vitest";

/**
 * A control whose write waits for the server shows it is working.
 *
 * A button that only greys out while its write is out reads as broken —
 * nothing says the click was taken. The standard (see
 * `.claude/rules/frontend_writes.md` → "Writes that wait"): the control that
 * fires such a write is a `<PendingButton pending={…}>`, which spins and is
 * busy as well as disabled.
 *
 * This scan finds every plain `<button>` whose `disabled` reads a pending
 * flag of a write that waits — a mutation in the same file whose `onMutate`
 * returns no `restore` (one that does answers on click, and its button only
 * needs the double-submit guard), a per-row tracker such a mutation begins,
 * or a pending flag handed down as a prop — and fails unless the button is
 * a dialog's cancel. The behavioural half is in
 * `e2e/budget-instant-actions.spec.ts`.
 *
 * Source is read through `import.meta.glob` rather than `node:fs` because
 * `tsconfig.app.json` is browser-only.
 */

const SOURCES = import.meta.glob("./**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** A prop or local carrying "a write is out", as the app names them. */
const PENDING_FLAG = /\b(isPending|isSubmitting|isSaving|isGenerating|isApplying|covering|saving)\b(?!\s*\()/;

/** The text of the object literal opening at `start` (its `{`), braces balanced. */
function balanced(source: string, start: number): string {
  let depth = 0;
  for (let i = start; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) return source.slice(start, i + 1);
  }
  return source.slice(start);
}

/** `useMutation` blocks by the name they are assigned to. */
function mutations(source: string): Map<string, string> {
  const found = new Map<string, string>();
  for (const match of source.matchAll(/const (\w+) = useMutation\(\{/g)) {
    found.set(match[1], balanced(source, match.index + match[0].length - 1));
  }
  return found;
}

/** Every plain `<button …>` opening tag, attributes and all. */
function buttonTags(source: string): string[] {
  const tags: string[] = [];
  for (const match of source.matchAll(/<button\b/g)) {
    let depth = 0;
    for (let i = match.index; i < source.length; i++) {
      const c = source[i];
      if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0 && source[i - 1] !== "=") {
        tags.push(source.slice(match.index, i + 1));
        break;
      }
    }
  }
  return tags;
}

/** The expression inside a tag's `disabled={…}`, if it has one. */
function disabledExpression(tag: string): string | null {
  const at = tag.indexOf("disabled={");
  return at === -1 ? null : balanced(tag, at + "disabled=".length).slice(1, -1);
}

/** Whether a button is a dialog's way out rather than the write's trigger. */
const isCancel = (tag: string) => /onClick=\{\s*(onClose|onCancel)\s*\}/.test(tag);

/**
 * The plain buttons in one source that disable on a waiting write: what the
 * scan below asks to be `PendingButton`s.
 */
function waitingButtons(source: string): string[] {
  const writes = mutations(source);
  const waiting = new Set([...writes].filter(([, block]) => !block.includes("restore")).map(([n]) => n));
  // `usePendingRows` trackers each waiting mutation begins.
  const trackers = new Set<string>();
  for (const name of waiting) {
    for (const begun of writes.get(name)!.matchAll(/(\w+)\.begin\(/g)) trackers.add(begun[1]);
  }
  const answersOnClick = new Set([...writes.keys()].filter((name) => !waiting.has(name)));

  return buttonTags(source).filter((tag) => {
    const expression = disabledExpression(tag);
    if (expression === null || isCancel(tag)) return false;
    for (const ref of expression.matchAll(/(\w+)\.isPending\b/g)) {
      if (waiting.has(ref[1]) || trackers.has(ref[1])) return true;
    }
    const bare = expression.replace(/\w+\.isPending\b(\([^)]*\))?/g, "");
    return PENDING_FLAG.test(bare) && ![...answersOnClick].some((name) => bare.includes(name));
  });
}

const COMPONENTS = Object.entries(SOURCES).filter(
  ([path]) => !path.endsWith(".test.tsx") && !path.endsWith("PendingButton.tsx"),
);

describe("controls of writes that wait for the server", () => {
  it("are PendingButtons, so they spin rather than only grey out", () => {
    const offenders = COMPONENTS.flatMap(([path, source]) =>
      waitingButtons(source).map((tag) => `${path}: ${tag.replace(/\s+/g, " ").slice(0, 140)}`),
    );
    expect(offenders).toEqual([]);
  });

  it("finds a plain button that only greys out while its write waits", () => {
    const source = `
      const save = useMutation({ mutationFn: api.save, onMutate: () => ({ refresh: {} }) });
      return <button onClick={() => save.mutate()} disabled={save.isPending}>Save</button>;
    `;
    expect(waitingButtons(source)).toHaveLength(1);
  });

  it("lets a write that answers on click keep a plain double-submit guard", () => {
    const source = `
      const mark = useMutation({ mutationFn: api.mark, onMutate: () => ({ restore }) });
      return <button onClick={() => mark.mutate()} disabled={mark.isPending}>Mark</button>;
    `;
    expect(waitingButtons(source)).toEqual([]);
  });

  it("lets a dialog's cancel disable while the write is out", () => {
    const source = `<button onClick={onClose} disabled={isPending}>Cancel</button>`;
    expect(waitingButtons(source)).toEqual([]);
  });

  it("finds a waiting write's per-row tracker and a pending flag handed down as a prop", () => {
    const rows = `
      const fund = useMutation({ mutationFn: api.fund, onMutate: (id) => { pending.begin(id); return plan; } });
      return <button onClick={() => fund.mutate(1)} disabled={pending.isPending(1)}>Fund</button>;
    `;
    expect(waitingButtons(rows)).toHaveLength(1);
    expect(waitingButtons(`<button onClick={onSubmit} disabled={!valid || isPending}>Save</button>`)).toHaveLength(1);
  });
});
