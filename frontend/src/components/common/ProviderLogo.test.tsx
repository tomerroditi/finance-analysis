import { describe, it, expect } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { ProviderLogo } from "./ProviderLogo";
import { renderWithProviders } from "../../test-utils";

describe("ProviderLogo", () => {
  it("renders the bundled logo for a known bank provider", () => {
    renderWithProviders(
      <ProviderLogo provider="hapoalim" service="banks" alt="Hapoalim" />,
    );
    const img = screen.getByAltText("Hapoalim") as HTMLImageElement;
    expect(img).toBeInTheDocument();
    expect(img.tagName).toBe("IMG");
    expect(img.src).toMatch(/hapoalim/i);
  });

  it("normalises provider keys with spaces to hyphenated filenames", () => {
    renderWithProviders(
      <ProviderLogo provider="visa cal" service="credit_cards" alt="Cal" />,
    );
    const img = screen.getByAltText("Cal") as HTMLImageElement;
    expect(img.src).toMatch(/visa-cal/i);
  });

  it("supports PNG logos (Beyahad Bishvilha)", () => {
    renderWithProviders(
      <ProviderLogo
        provider="beyahad bishvilha"
        service="credit_cards"
        alt="Beyahad"
      />,
    );
    const img = screen.getByAltText("Beyahad") as HTMLImageElement;
    expect(img.src).toMatch(/beyahad-bishvilha\.png/i);
  });

  it("falls back to the bank icon when the provider is unknown", () => {
    const { container } = renderWithProviders(
      <ProviderLogo provider="totally-fake-bank" service="banks" />,
    );
    // Lucide icons render as <svg> with class names containing "lucide".
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("class") ?? "").toMatch(/lucide-landmark/i);
  });

  it("falls back to the credit-card icon for an unknown credit-card provider", () => {
    const { container } = renderWithProviders(
      <ProviderLogo provider="unknown" service="credit_cards" />,
    );
    expect(container.querySelector("svg")?.getAttribute("class") ?? "").toMatch(
      /lucide-credit-card/i,
    );
  });

  it("falls back to the shield icon for insurance providers", () => {
    const { container } = renderWithProviders(
      <ProviderLogo provider="unknown" service="insurances" />,
    );
    expect(container.querySelector("svg")?.getAttribute("class") ?? "").toMatch(
      /lucide-shield/i,
    );
  });

  it("falls back to the service icon if the image fails to load at runtime", () => {
    const { container } = renderWithProviders(
      <ProviderLogo provider="hapoalim" service="banks" alt="Hapoalim" />,
    );
    const img = screen.getByAltText("Hapoalim") as HTMLImageElement;
    // Simulate a load error (broken URL, blocked by CSP, etc.) and verify the
    // component swaps in the generic bank icon instead of showing a broken img.
    fireEvent.error(img);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("class") ?? "").toMatch(/lucide-landmark/i);
  });
});
