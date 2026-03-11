import {
    Plus,
    Trash2,
    CornerDownRight,
    Layers,
    FileText
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ConditionNode, ConditionType, Operator } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";

interface RuleBuilderProps {
    value: ConditionNode;
    onChange: (value: ConditionNode) => void;
    depth?: number;
    onRemove?: () => void;
}

const FIELDS = [
    { value: "description", labelKey: "description", type: "text" },
    { value: "amount", labelKey: "amount", type: "number" },
    { value: "provider", labelKey: "provider", type: "text" },
    { value: "account_name", labelKey: "accountName", type: "text" },
    { value: "service", labelKey: "service", type: "text" },
];

const OPERATORS: Record<string, { value: string; labelKey: string }[]> = {
    text: [
        { value: "contains", labelKey: "contains" },
        { value: "equals", labelKey: "equals" },
        { value: "starts_with", labelKey: "startsWith" },
        { value: "ends_with", labelKey: "endsWith" },
    ],
    number: [
        { value: "equals", labelKey: "equals" },
        { value: "gt", labelKey: "greaterThan" },
        { value: "lt", labelKey: "lessThan" },
        { value: "gte", labelKey: "greaterOrEqual" },
        { value: "lte", labelKey: "lessOrEqual" },
        { value: "between", labelKey: "between" },
    ],
};

export function RuleBuilder({ value, onChange, depth = 0, onRemove }: RuleBuilderProps) {
    const { t } = useTranslation();
    const isGroup = value.type === "AND" || value.type === "OR";

    const handleFieldChange = (field: string) => {
        // Reset operator and value when field type changes
        const fieldDef = FIELDS.find(f => f.value === field);
        const defaultOp = fieldDef?.type === "number" ? "equals" : "contains";
        onChange({ ...value, field, operator: defaultOp as Operator, value: "" });
    };

    const addSubCondition = (type: ConditionType) => {
        const newNode: ConditionNode = type === "CONDITION"
            ? { type: "CONDITION", field: "description", operator: "contains", value: "" }
            : { type, subconditions: [] };

        onChange({
            ...value,
            subconditions: [newNode, ...(value.subconditions || [])]
        });
    };

    const updateSubCondition = (index: number, newSub: ConditionNode) => {
        const newSubs = [...(value.subconditions || [])];
        newSubs[index] = newSub;
        onChange({ ...value, subconditions: newSubs });
    };

    const removeSubCondition = (index: number) => {
        const newSubs = (value.subconditions || []).filter((_, i) => i !== index);
        onChange({ ...value, subconditions: newSubs });
    };

    if (isGroup) {
        return (
            <div className={`
              rounded-xl border border-[var(--surface-light)] 
              ${depth === 0 ? 'bg-[var(--surface-base)]' : 'bg-[var(--surface)] mt-2'}
              overflow-hidden transition-all
          `}>
                {/* Group Header */}
                <div className="flex items-center gap-2 p-2 bg-[var(--surface-light)]/20 border-b border-[var(--surface-light)]">
                    <div className="flex items-center gap-1">
                        <Layers size={14} className="text-[var(--primary)]" />
                        <div className="w-40">
                        <SelectDropdown
                            options={[
                                { label: t("ruleBuilder.andAllMatch"), value: "AND" },
                                { label: t("ruleBuilder.orAnyMatch"), value: "OR" },
                            ]}
                            value={value.type}
                            onChange={(val) => onChange({ ...value, type: val as "AND" | "OR" })}
                            size="sm"
                        />
                        </div>
                    </div>

                    <div className="flex-1" />

                    <div className="flex gap-1">
                        <button
                            onClick={() => addSubCondition("CONDITION")}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--surface)] hover:bg-[var(--surface-light)] text-[10px] font-bold border border-[var(--surface-light)]"
                        >
                            <Plus size={10} /> {t("ruleBuilder.condition")}
                        </button>
                        <button
                            onClick={() => addSubCondition("AND")}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--surface)] hover:bg-[var(--surface-light)] text-[10px] font-bold border border-[var(--surface-light)]"
                        >
                            <Plus size={10} /> {t("ruleBuilder.group")}
                        </button>
                        {depth > 0 && onRemove && (
                            <button
                                onClick={onRemove}
                                className="p-1 rounded hover:bg-red-500/10 text-red-400"
                                title={t("ruleBuilder.deleteGroup")}
                            >
                                <Trash2 size={12} />
                            </button>
                        )}
                    </div>
                </div>

                {/* Group Content */}
                <div className="p-3 ps-2 space-y-2">
                    {(!value.subconditions || value.subconditions.length === 0) && (
                        <div className="text-center py-4 text-xs text-[var(--text-muted)] italic border border-dashed border-[var(--surface-light)] rounded-lg">
                            {t("ruleBuilder.emptyGroup")}
                        </div>
                    )}
                    {value.subconditions?.map((sub, idx) => (
                        <div key={idx} className="flex gap-2">
                            <div className="flex flex-col items-center pt-2">
                                <CornerDownRight size={14} className="text-[var(--text-muted)]" />
                                {idx < (value.subconditions?.length || 0) - 1 && (
                                    <div className="w-px h-full bg-[var(--surface-light)] my-1" />
                                )}
                            </div>
                            <div className="flex-1">
                                <RuleBuilder
                                    value={sub}
                                    onChange={(newSub) => updateSubCondition(idx, newSub)}
                                    depth={depth + 1}
                                    onRemove={() => removeSubCondition(idx)}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    // Single Condition View
    const fieldDef = FIELDS.find(f => f.value === value.field) || FIELDS[0];
    const inputType = fieldDef.type === "number" ? "number" : "text";
    const operators = OPERATORS[fieldDef.type] || OPERATORS.text;

    return (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/30 transition-all">
            <div className="p-1.5 rounded bg-[var(--surface)] text-[var(--text-muted)]">
                <FileText size={14} />
            </div>

            <div className="w-32">
            <SelectDropdown
                options={FIELDS.map(f => ({ label: t(`ruleBuilder.${f.labelKey}`), value: f.value }))}
                value={value.field || "description"}
                onChange={(val) => handleFieldChange(val)}
                size="sm"
            />
            </div>

            <div className="w-32">
            <SelectDropdown
                options={operators.map(op => ({ label: t(`ruleBuilder.${op.labelKey}`), value: op.value }))}
                value={value.operator || "contains"}
                onChange={(val) => onChange({ ...value, operator: val as Operator })}
                size="sm"
            />
            </div>

            {value.operator === "between" ? (
                <div className="flex items-center gap-1">
                    <input
                        type="number"
                        placeholder={t("ruleBuilder.min")}
                        value={Array.isArray(value.value) ? value.value[0] : ""}
                        onChange={(e) => onChange({
                            ...value,
                            value: [Number(e.target.value), Array.isArray(value.value) ? value.value[1] : 0]
                        })}
                        className="w-20 bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-xs outline-none focus:border-[var(--primary)]"
                    />
                    <span className="text-xs text-[var(--text-muted)]">-</span>
                    <input
                        type="number"
                        placeholder={t("ruleBuilder.max")}
                        value={Array.isArray(value.value) ? value.value[1] : ""}
                        onChange={(e) => onChange({
                            ...value,
                            value: [Array.isArray(value.value) ? value.value[0] : 0, Number(e.target.value)]
                        })}
                        className="w-20 bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-xs outline-none focus:border-[var(--primary)]"
                    />
                </div>
            ) : (
                <input
                    type={inputType}
                    placeholder={t("ruleBuilder.value")}
                    value={value.value != null && typeof value.value !== "boolean" && !Array.isArray(value.value) ? value.value : ""}
                    onChange={(e) => onChange({ ...value, value: inputType === 'number' ? Number(e.target.value) : e.target.value })}
                    className="flex-1 min-w-[100px] bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-xs outline-none focus:border-[var(--primary)]"
                />
            )}

            {onRemove && (
                <button
                    onClick={onRemove}
                    className="p-1 rounded hover:bg-red-500/10 text-red-400 transition-colors"
                >
                    <Trash2 size={14} />
                </button>
            )}
        </div>
    );
}
