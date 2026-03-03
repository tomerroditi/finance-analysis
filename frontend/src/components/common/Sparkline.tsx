import { useId } from "react";

interface SparklineProps {
    data: number[];
    width?: number;
    height?: number;
    color?: string;
    className?: string;
}

export function Sparkline({
    data,
    width = 80,
    height = 24,
    color = "var(--primary)",
    className,
}: SparklineProps) {
    const id = useId();

    if (data.length < 2) return null;

    const padding = 2;
    const innerWidth = width - padding * 2;
    const innerHeight = height - padding * 2;

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    const points = data.map((value, i) => ({
        x: padding + (i / (data.length - 1)) * innerWidth,
        y: padding + innerHeight - ((value - min) / range) * innerHeight,
    }));

    const linePath = points
        .map((p, i) => {
            if (i === 0) return `M ${p.x} ${p.y}`;
            // Step: horizontal to new x, then vertical to new y
            return `L ${p.x} ${points[i - 1].y} L ${p.x} ${p.y}`;
        })
        .join(" ");

    const areaPath = `${linePath} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`;

    const gradientId = `sparkline-grad-${id}`;

    return (
        <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className={className}
        >
            <defs>
                <linearGradient
                    id={gradientId}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                >
                    <stop
                        offset="0%"
                        stopColor={color}
                        stopOpacity="0.3"
                    />
                    <stop
                        offset="100%"
                        stopColor={color}
                        stopOpacity="0"
                    />
                </linearGradient>
            </defs>
            <path d={areaPath} fill={`url(#${gradientId})`} />
            <path
                d={linePath}
                fill="none"
                stroke={color}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}
