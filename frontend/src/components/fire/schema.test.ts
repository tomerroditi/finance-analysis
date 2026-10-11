import { describe, expect, it } from "vitest";
import en from "../../locales/en.json";
import he from "../../locales/he.json";
import {
  SECTIONS,
  fieldLabelKey,
  helpKey,
  holds,
  initialScenario,
  isFieldVisible,
  swapRows,
  type FieldSpec,
} from "./schema";

function lookup(locale: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>(
    (node, part) => (node && typeof node === "object" ? (node as Record<string, unknown>)[part] : undefined),
    locale,
  );
}

function field(sectionKey: string, name: string): FieldSpec {
  const found = SECTIONS.find((s) => s.key === sectionKey)?.fields.find((f) => f.name === name);
  if (!found) throw new Error(`${sectionKey}.${name} is not in the schema`);
  return found;
}

const visibleFields = SECTIONS.flatMap((section) =>
  section.fields.filter((f) => f.kind !== "hidden").map((f) => ({ section: section.key, field: f })),
);

describe("field explanations", () => {
  it.each(visibleFields.map(({ section, field: f }) => [`${section}.${f.name}`, f] as const))(
    "%s is explained in both languages",
    (_name, f) => {
      for (const locale of [en, he]) expect(typeof lookup(locale, helpKey(f))).toBe("string");
    },
  );

  it("explains every problem the solver can be asked", () => {
    const options = field("problem", "base_problem").options ?? [];
    for (const option of options) {
      for (const locale of [en, he]) {
        expect(typeof lookup(locale, `fire.hint.problemFor.${option.value}`)).toBe("string");
      }
    }
  });
});

describe("one-time rows", () => {
  it.each(["expense", "income"])("a one-time %s row asks only for a date and an amount", (prefix) => {
    const section = prefix;
    const fields = { ...initialScenario(), [`${prefix}StartType1`]: "one_time" };
    const shown = SECTIONS.find((s) => s.key === section)!
      .fields.filter((f) => f.kind !== "hidden" && isFieldVisible(f, fields, "1"))
      .map((f) => f.name);
    expect(shown).toEqual([`${prefix}StartType`, `${prefix}StartDate`, `${prefix}Sum`, `${prefix}Description`]);
    expect(fieldLabelKey(field(section, `${prefix}StartDate`), fields, "1")).toBe("fire.field.paymentDate");
  });

  it("a recurring row ending on a date shows its end date", () => {
    const fields = { ...initialScenario(), expenseStartType1: "from_date", expenseEndType1: "to_date" };
    expect(isFieldVisible(field("expense", "expenseEndDate"), fields, "1")).toBe(true);
    expect(isFieldVisible(field("expense", "expenseRise"), fields, "1")).toBe(true);
    expect(fieldLabelKey(field("expense", "expenseStartDate"), fields, "1")).toBe("fire.field.startDate");
  });
});

describe("what the reference shows", () => {
  it("asks for the maximum age only when retiring as early as possible", () => {
    const maxAge = field("problem", "base_problem_max_age");
    expect(isFieldVisible(maxAge, { base_problem: "retire_asap" })).toBe(true);
    expect(isFieldVisible(maxAge, { base_problem: "retire_at_age" })).toBe(false);
  });

  it("hides the partner's pension until a partner is included", () => {
    const condition = SECTIONS.find((s) => s.key === "partnerPension")!.visibleWhen!;
    expect(holds(condition, { pensionTake_2: "" })).toBe(false);
    expect(holds(condition, { pensionTake_2: "on" })).toBe(true);
  });
});

describe("swapRows", () => {
  it("swaps every field of two rows, the tracked-account link included", () => {
    const portfolio = SECTIONS.find((s) => s.key === "portfolio")!;
    expect(portfolio.reorderable).toBe(true);
    const fields = {
      num_portfolio_fields: "2",
      portfolioBalance1: "100",
      portfolioSource1: "investment:1",
      portfolioBalance2: "200",
      portfolioSource2: "",
    };
    const swapped = swapRows(fields, portfolio, 1, 2);
    expect(swapped.portfolioBalance1).toBe("200");
    expect(swapped.portfolioSource1).toBe("");
    expect(swapped.portfolioBalance2).toBe("100");
    expect(swapped.portfolioSource2).toBe("investment:1");
    expect(swapped.num_portfolio_fields).toBe("2");
  });
});
