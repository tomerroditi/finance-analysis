import Plot from 'react-plotly.js';
import { useMemo } from 'react';

interface SankeyData {
    nodes: number[]; // Indices
    node_labels: string[];
    links: {
        source: number;
        target: number;
        value: number;
        label: string;
    }[];
}

interface SankeyChartProps {
    data: SankeyData;
    height?: number;
}

export function SankeyChart({ data, height = 500 }: SankeyChartProps) {
    const plotData = useMemo(() => {
        if (!data || data.nodes.length === 0) return [];

        return [{
            type: "sankey",
            orientation: "h",
            node: {
                pad: 15,
                thickness: 20,
                line: {
                    color: "black",
                    width: 0.5
                },
                label: data.node_labels,
                color: data.node_labels.map((_, i) => {
                    // Simple color cycling
                    const colors = [
                        "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
                        "#ec4899", "#6366f1", "#14b8a6", "#f97316", "#06b6d4"
                    ];
                    return colors[i % colors.length];
                })
            },
            link: {
                source: data.links.map(l => l.source),
                target: data.links.map(l => l.target),
                value: data.links.map(l => l.value),
                // color: "rgba(100, 100, 100, 0.2)" // semi-transparent gray
            }
        }];
    }, [data]);

    const layout = {
        font: {
            size: 12,
            color: "#94a3b8",
            family: "Inter, sans-serif"
        },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { t: 20, b: 20, l: 20, r: 20 },
        height: height,
        autosize: true
    };

    if (!data || !data.nodes || !data.nodes.length) {
        return (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
                No data available for the selected period
            </div>
        );
    }

    return (
        <Plot
            data={plotData as any}
            layout={layout as any}
            useResizeHandler={true}
            style={{ width: "100%", height: "100%" }}
            config={{ displayModeBar: false, responsive: true }}
        />
    );
}
