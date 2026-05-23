import { describe, it, expect } from "vitest";
import { useState } from "react";
import { screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { RuleBuilder } from "./RuleBuilder";
import type { ConditionNode } from "../../services/api";

function StatefulRuleBuilder({ initial }: { initial: ConditionNode }) {
    const [node, setNode] = useState<ConditionNode>(initial);
    return (
        <>
            <RuleBuilder value={node} onChange={setNode} />
            <div data-testid="captured-value">{JSON.stringify(node.value)}</div>
        </>
    );
}

describe("RuleBuilder amount input", () => {
    it("captures a negative number typed into the amount value input", async () => {
        const user = userEvent.setup();
        const initial: ConditionNode = {
            type: "CONDITION",
            field: "amount",
            operator: "lt",
            value: "",
        };

        renderWithProviders(<StatefulRuleBuilder initial={initial} />);

        const valueInput = screen.getByPlaceholderText("Value");
        await user.type(valueInput, "-100");

        expect(screen.getByTestId("captured-value").textContent).toBe("-100");
    });

    it("captures a negative number typed into the 'between' min input", async () => {
        const user = userEvent.setup();
        const initial: ConditionNode = {
            type: "CONDITION",
            field: "amount",
            operator: "between",
            value: ["", ""],
        };

        renderWithProviders(<StatefulRuleBuilder initial={initial} />);

        const minInput = screen.getByPlaceholderText("Min");
        await user.type(minInput, "-50");

        expect(screen.getByTestId("captured-value").textContent).toBe('[-50,""]');
    });

    it("captures a positive number typed into the amount value input", async () => {
        const user = userEvent.setup();
        const initial: ConditionNode = {
            type: "CONDITION",
            field: "amount",
            operator: "gt",
            value: "",
        };

        renderWithProviders(<StatefulRuleBuilder initial={initial} />);

        const valueInput = screen.getByPlaceholderText("Value");
        await user.type(valueInput, "250");

        expect(screen.getByTestId("captured-value").textContent).toBe("250");
    });

    it("captures a decimal number typed into the amount value input", async () => {
        const user = userEvent.setup();
        const initial: ConditionNode = {
            type: "CONDITION",
            field: "amount",
            operator: "gt",
            value: "",
        };

        renderWithProviders(<StatefulRuleBuilder initial={initial} />);

        const valueInput = screen.getByPlaceholderText("Value");
        await user.type(valueInput, "-12.5");

        expect(screen.getByTestId("captured-value").textContent).toBe("-12.5");
    });

    it("uses a text input that preserves a lone '-' character during typing", () => {
        const initial: ConditionNode = {
            type: "CONDITION",
            field: "amount",
            operator: "lt",
            value: "",
        };

        renderWithProviders(<StatefulRuleBuilder initial={initial} />);

        const valueInput = screen.getByPlaceholderText("Value") as HTMLInputElement;
        expect(valueInput.type).toBe("text");
        expect(valueInput.inputMode).toBe("decimal");

        fireEvent.input(valueInput, { target: { value: "-" } });
        expect(valueInput.value).toBe("-");
    });
});
