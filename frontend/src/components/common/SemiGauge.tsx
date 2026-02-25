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
    }).format(n || 0);

function getGaugeColor(percentage: number): string {
    if (percentage > 100) return "#ef4444";
    if (percentage >= 75) return "#f59e0b";
    return "#22c55e";
}

export function SemiGauge({
    spent,
    budget,
    size = 220,
    className,
}: SemiGaugeProps) {
    const percentage = budget > 0 ? (spent / budget) * 100 : 0;
    const color = getGaugeColor(percentage);

    const strokeWidth = 14;
    const cx = size / 2;
    const cy = size / 2;
    const r = cx - strokeWidth;

    // Arc lengths: using stroke-dasharray on a circle
    const circumference = 2 * Math.PI * r;
    const semicircle = circumference / 2;

    // Fill: percentage of the semicircle, capped at 120% visually
    const fillRatio = Math.min(percentage, 120) / 100;
    const fillLength = fillRatio * semicircle;

    // SVG only needs the top half of the circle + padding for stroke
    const svgHeight = cy + strokeWidth;

    return (
        <div className={className}>
            <svg
                width={size}
                height={svgHeight}
                viewBox={`0 0 ${size} ${svgHeight}`}
            >
                {/* Background track: full semicircle */}
                <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill="none"
                    stroke="var(--surface-light)"
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeDasharray={`${semicircle} ${circumference}`}
                    transform={`rotate(180 ${cx} ${cy})`}
                />

                {/* Filled arc */}
                {spent > 0 && budget > 0 && (
                    <circle
                        cx={cx}
                        cy={cy}
                        r={r}
                        fill="none"
                        stroke={color}
                        strokeWidth={strokeWidth}
                        strokeLinecap="round"
                        strokeDasharray={`${fillLength} ${circumference}`}
                        transform={`rotate(180 ${cx} ${cy})`}
                    />
                )}

                {/* Center text: spent amount */}
                <text
                    x={cx}
                    y={cy - 24}
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
                    y={cy - 2}
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
