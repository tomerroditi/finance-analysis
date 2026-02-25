interface SkeletonProps {
    className?: string;
    variant?: "text" | "card" | "chart" | "circle";
    lines?: number;
}

export function Skeleton({
    className = "",
    variant = "text",
    lines = 3,
}: SkeletonProps) {
    if (variant === "text") {
        return (
            <div className={`space-y-2 ${className}`}>
                {Array.from({ length: lines }, (_, i) => (
                    <div
                        key={i}
                        className={`h-4 rounded bg-[var(--surface-light)] animate-pulse ${
                            lines > 1 && i === lines - 1 ? "w-3/4" : "w-full"
                        }`}
                    />
                ))}
            </div>
        );
    }

    if (variant === "card") {
        return (
            <div
                className={`rounded-lg bg-[var(--surface-light)] animate-pulse ${className}`}
            />
        );
    }

    if (variant === "chart") {
        return (
            <div
                className={`h-64 rounded-lg bg-[var(--surface-light)] animate-pulse ${className}`}
            />
        );
    }

    // circle
    return (
        <div
            className={`rounded-full bg-[var(--surface-light)] animate-pulse ${className}`}
        />
    );
}
