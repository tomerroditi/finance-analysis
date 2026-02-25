interface SemiGaugeProps {
    spent: number;
    budget: number;
    size?: number;
    className?: string;
}

const formatCurrency = (n: number) =>
    new Intl.NumberFormat("he-IL", {
        style: "currency",
        currency: "ILS",
        maximumFractionDigits: 0,
    }).format(n);

function getGaugeColor(percentage: number): string {
    if (percentage > 100) return "#ef4444";
    if (percentage >= 75) return "#f59e0b";
    return "#22c55e";
}

function describeArc(
    cx: number,
    cy: number,
    r: number,
    startAngle: number,
    endAngle: number,
): string {
    const startX = cx + r * Math.cos(startAngle);
    const startY = cy - r * Math.sin(startAngle);
    const endX = cx + r * Math.cos(endAngle);
    const endY = cy - r * Math.sin(endAngle);

    // The arc spans from startAngle down to endAngle (going clockwise in SVG).
    // Since startAngle = π and endAngle decreases toward 0, the angular span
    // is startAngle - endAngle. largeArcFlag = 1 when span > π.
    const angularSpan = startAngle - endAngle;
    const largeArcFlag = angularSpan > Math.PI ? 1 : 0;

    // sweep-flag = 0 for clockwise in standard math (which is counterclockwise
    // in SVG's flipped y-axis, but since we negate sin for y, we use sweep = 0
    // to go from left to right along the top of the semicircle).
    return `M ${startX} ${startY} A ${r} ${r} 0 ${largeArcFlag} 0 ${endX} ${endY}`;
}

export function SemiGauge({
    spent,
    budget,
    size = 220,
    className,
}: SemiGaugeProps) {
    const percentage = budget > 0 ? (spent / budget) * 100 : 0;
    const color = getGaugeColor(percentage);

    const cx = size / 2;
    const cy = size / 2 + 10;
    const r = size / 2 - 16;

    // Background arc: full semicircle from π (left) to 0 (right)
    const bgPath = describeArc(cx, cy, r, Math.PI, 0);

    // Filled arc: proportional to percentage, capped at 120% visually
    const fillRatio = Math.min(percentage, 120) / 100;
    const showFilled = spent > 0 && budget > 0;

    // The filled arc goes from π toward 0. At 100%, endAngle = 0.
    // At 120%, endAngle goes slightly past 0 — but we cap at 0 since
    // our semicircle only spans π to 0. We map 0–120% to π–0 range.
    const filledEndAngle = Math.PI * (1 - fillRatio);
    const filledPath = showFilled
        ? describeArc(cx, cy, r, Math.PI, Math.max(filledEndAngle, 0))
        : "";

    // SVG height: only need the top half of the circle plus some padding
    const svgHeight = cy + 4;

    return (
        <div className={className}>
            <svg
                width={size}
                height={svgHeight}
                viewBox={`0 0 ${size} ${svgHeight}`}
            >
                {/* Background arc */}
                <path
                    d={bgPath}
                    fill="none"
                    stroke="var(--surface-light)"
                    strokeWidth={12}
                    strokeLinecap="round"
                />

                {/* Filled arc */}
                {showFilled && (
                    <path
                        d={filledPath}
                        fill="none"
                        stroke={color}
                        strokeWidth={12}
                        strokeLinecap="round"
                    />
                )}

                {/* Center text: spent amount */}
                <text
                    x={cx}
                    y={cy - 28}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="currentColor"
                    fontSize={24}
                    fontWeight={700}
                >
                    {formatCurrency(spent)}
                </text>

                {/* Subtext: of budget */}
                <text
                    x={cx}
                    y={cy - 4}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="var(--text-muted)"
                    fontSize={14}
                >
                    of {formatCurrency(budget)}
                </text>
            </svg>

            {/* Percentage text below the SVG */}
            <p
                className="text-center text-sm font-medium -mt-1"
                style={{ color }}
            >
                {Math.round(percentage)}% used
            </p>
        </div>
    );
}
