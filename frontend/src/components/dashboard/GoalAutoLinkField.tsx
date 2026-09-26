import { useTranslation } from "react-i18next";
import { useCategories } from "../../hooks/useCategories";
import { SelectDropdown } from "../common/SelectDropdown";
import { MultiSelect } from "../common/MultiSelect";

/**
 * One category + tags rule on a savings goal: every matching transaction is
 * linked to the goal automatically, now and as new ones arrive.
 *
 * An empty category turns the rule off; no tags means every tag in the
 * category.
 */
export function GoalAutoLinkField({
  label,
  hint,
  category,
  tags,
  onChange,
  testId,
}: {
  label: string;
  hint: string;
  category: string;
  tags: string[];
  onChange: (category: string, tags: string[]) => void;
  testId?: string;
}) {
  const { t } = useTranslation();
  const { data: categoriesMap } = useCategories();
  const categories = Object.keys(categoriesMap ?? {});
  const tagOptions = (category && categoriesMap?.[category]) || [];

  return (
    <div data-testid={testId}>
      <span className="block text-xs font-medium text-[var(--text-muted)] mb-1">{label}</span>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <SelectDropdown
          options={[
            { label: t("dashboard.goals.autoLinkNone"), value: "" },
            ...categories.map((c) => ({ label: c, value: c })),
          ]}
          value={category}
          onChange={(value) => onChange(value, [])}
          placeholder={t("dashboard.goals.autoLinkNone")}
          size="sm"
        />
        {category ? (
          <MultiSelect
            options={tagOptions}
            selected={tags}
            onChange={(next) => onChange(category, next)}
            placeholder={t("dashboard.goals.autoLinkAllTags")}
          />
        ) : (
          <span />
        )}
      </div>
      <p className="text-[10px] text-[var(--text-muted)] mt-1">{hint}</p>
    </div>
  );
}
