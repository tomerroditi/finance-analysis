import { describe, it, expect, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { useScrollCap } from "./useScrollCap";

/**
 * jsdom lays nothing out, so every height it reports is 0. Stand in a content
 * height for the one measurement the cap is decided on.
 */
function withContentHeight(height: number) {
  const original = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "scrollHeight",
  );
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
    configurable: true,
    get: () => height,
  });
  return () => {
    if (original) {
      Object.defineProperty(HTMLElement.prototype, "scrollHeight", original);
    }
  };
}

let restore: (() => void) | null = null;
afterEach(() => {
  restore?.();
  restore = null;
});

function Probe({ cap, slack }: { cap: number; slack?: number }) {
  const [ref, capped] = useScrollCap(cap, undefined, slack);
  return (
    <div ref={ref} data-testid="list">
      {String(capped)}
    </div>
  );
}

describe("useScrollCap", () => {
  it("caps a list that runs well past the cap", () => {
    restore = withContentHeight(900);

    render(<Probe cap={416} />);

    expect(screen.getByTestId("list")).toHaveTextContent("true");
  });

  it("leaves a list that would barely scroll uncapped", () => {
    // 20px past the cap: nothing worth reaching, and a scroll region here
    // swallows the drag that was meant to scroll the page.
    restore = withContentHeight(436);

    render(<Probe cap={416} />);

    expect(screen.getByTestId("list")).toHaveTextContent("false");
  });

  it("treats the slack as the threshold, not the cap", () => {
    // Past the cap by more than the caller's slack, but less than the default.
    restore = withContentHeight(466);

    render(<Probe cap={416} slack={40} />);

    expect(screen.getByTestId("list")).toHaveTextContent("true");
  });

  it("leaves a list that fits uncapped", () => {
    restore = withContentHeight(100);

    render(<Probe cap={416} />);

    expect(screen.getByTestId("list")).toHaveTextContent("false");
  });
});
