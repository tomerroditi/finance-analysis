import { useState, useRef, useCallback, useEffect, type ReactNode } from "react";

interface ResizableSplitPaneProps {
    left: ReactNode;
    right: ReactNode;
    defaultLeftWidth?: number;
    minLeftWidth?: number;
    minRightWidth?: number;
    storageKey?: string;
}

export function ResizableSplitPane({
    left,
    right,
    defaultLeftWidth = 50,
    minLeftWidth = 20,
    minRightWidth = 20,
    storageKey = "split-pane-width"
}: ResizableSplitPaneProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [leftWidth, setLeftWidth] = useState(() => {
        if (storageKey) {
            const saved = localStorage.getItem(storageKey);
            if (saved) return parseFloat(saved);
        }
        return defaultLeftWidth;
    });
    const [isDragging, setIsDragging] = useState(false);

    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isDragging || !containerRef.current) return;

        const rect = containerRef.current.getBoundingClientRect();
        const newLeftWidth = ((e.clientX - rect.left) / rect.width) * 100;

        const clampedWidth = Math.max(minLeftWidth, Math.min(100 - minRightWidth, newLeftWidth));
        setLeftWidth(clampedWidth);
    }, [isDragging, minLeftWidth, minRightWidth]);

    const handleMouseUp = useCallback(() => {
        if (isDragging) {
            setIsDragging(false);
            if (storageKey) {
                localStorage.setItem(storageKey, leftWidth.toString());
            }
        }
    }, [isDragging, leftWidth, storageKey]);

    useEffect(() => {
        if (isDragging) {
            window.addEventListener("mousemove", handleMouseMove);
            window.addEventListener("mouseup", handleMouseUp);
            return () => {
                window.removeEventListener("mousemove", handleMouseMove);
                window.removeEventListener("mouseup", handleMouseUp);
            };
        }
    }, [isDragging, handleMouseMove, handleMouseUp]);

    return (
        <div ref={containerRef} className="flex h-full w-full select-none">
            {/* Left Pane */}
            <div style={{ width: `${leftWidth}%` }} className="h-full overflow-hidden">
                {left}
            </div>

            {/* Divider */}
            <div
                onMouseDown={handleMouseDown}
                className={`w-1 bg-[var(--surface-light)] hover:bg-[var(--primary)] cursor-col-resize transition-colors flex-shrink-0 relative group ${isDragging ? "bg-[var(--primary)]" : ""}`}
            >
                <div className="absolute inset-y-0 -start-1 -end-1" />
                <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1 h-8 rounded-full bg-[var(--text-muted)] opacity-0 group-hover:opacity-50 transition-opacity ${isDragging ? "opacity-50" : ""}`} />
            </div>

            {/* Right Pane */}
            <div style={{ width: `${100 - leftWidth}%` }} className="h-full overflow-hidden">
                {right}
            </div>
        </div>
    );
}
