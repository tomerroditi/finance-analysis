/**
 * Keeping a plan in step with tracked data, on the client.
 *
 * The server refreshes linked fields and sourced rows on every read
 * (`backend/services/fire_plan_service.py`). The form needs the same rules
 * while the user edits: typing over a tracked value detaches it, and "sync"
 * pulls in accounts the plan does not hold yet.
 */
import type { FirePlan } from "../../services/api";
import { SECTIONS, type SectionSpec } from "./schema";

export interface Draft {
  fields: Record<string, string>;
  linked: string[];
}

type Tracked = FirePlan["tracked"];

function rowCount(fields: Record<string, string>, section: SectionSpec): number {
  return Number(fields[`num_${section.repeatable?.countKey}_fields`] ?? 0);
}

/** The field stems a tracked row of this section keeps refreshing. */
function trackedStems(tracked: Tracked, section: SectionSpec): Set<string> {
  return new Set((tracked.rows[section.key] ?? []).flatMap((row) => Object.keys(row.fields)));
}

/**
 * Apply a typed value. A linked field stops following tracked data; a tracked
 * field of a sourced row detaches the whole row, which becomes the user's own.
 */
export function editField(draft: Draft, tracked: Tracked, name: string, value: string): Draft {
  const fields = { ...draft.fields, [name]: value };
  const linked = draft.linked.filter((n) => n !== name);
  for (const section of SECTIONS) {
    if (!section.sourceField) continue;
    const stems = trackedStems(tracked, section);
    for (let row = 1; row <= rowCount(fields, section); row += 1) {
      for (const stem of stems) {
        if (`${stem}${row}` === name) fields[`${section.sourceField}${row}`] = "";
      }
    }
  }
  return { fields, linked };
}

/** Make a single-value field follow tracked data again. */
export function relink(draft: Draft, tracked: Tracked, name: string): Draft {
  if (!(name in tracked.scalars)) return draft;
  return {
    fields: { ...draft.fields, [name]: tracked.scalars[name] },
    linked: [...new Set([...draft.linked, name])],
  };
}

/**
 * Bring the draft up to date: refresh what follows tracked data, and add a row
 * for every tracked account the plan does not hold yet.
 */
export function syncWithTracked(draft: Draft, tracked: Tracked): Draft {
  const fields = { ...draft.fields };
  for (const name of draft.linked) {
    if (name in tracked.scalars) fields[name] = tracked.scalars[name];
  }
  for (const section of SECTIONS) {
    const repeatable = section.repeatable;
    if (!repeatable || !section.sourceField) continue;
    const rows = tracked.rows[section.key] ?? [];
    let count = rowCount(fields, section);
    const held = new Set<string>();
    for (let row = 1; row <= count; row += 1) {
      const source = fields[`${section.sourceField}${row}`];
      const current = rows.find((r) => r.source === source);
      if (!source || !current) continue;
      held.add(source);
      for (const [stem, value] of Object.entries(current.fields)) fields[`${stem}${row}`] = value;
    }
    for (const trackedRow of rows) {
      if (held.has(trackedRow.source) || count >= repeatable.max) continue;
      count += 1;
      for (const field of section.fields) fields[`${field.name}${count}`] = field.default;
      for (const [stem, value] of Object.entries({ ...trackedRow.seed, ...trackedRow.fields })) {
        fields[`${stem}${count}`] = value;
      }
      fields[`${section.sourceField}${count}`] = trackedRow.source;
    }
    fields[`num_${repeatable.countKey}_fields`] = String(count);
  }
  return { fields, linked: draft.linked };
}

/** Tracked account names by source id, for the row badges. */
export function sourceLabels(tracked: Tracked): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const rows of Object.values(tracked.rows)) {
    for (const row of rows) labels[row.source] = row.label;
  }
  return labels;
}
