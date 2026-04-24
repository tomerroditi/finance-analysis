import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useDataFlowData } from "./useDataFlowData";
import type { DetailData } from "./dataFlowData";

interface Connection {
  from: string;
  to: string;
  color: string;
  path: string;
  animDur: number;
  animBegin: number;
}

export function DataFlowDiagram() {
  const { t } = useTranslation();
  const { layers, connectionDefs, details, callouts, platformFeatures } = useDataFlowData();
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const highlightedId = hoveredNode ?? activeNode;

  const connectedNodes = highlightedId
    ? new Set(
        connectionDefs
          .filter((c) => c.from === highlightedId || c.to === highlightedId)
          .flatMap((c) => [c.from, c.to]),
      )
    : null;

  const drawConnections = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const containerRect = container.getBoundingClientRect();
    const scrollLeft = container.scrollLeft;
    const scrollTop = container.scrollTop;

    setSvgSize({
      width: container.scrollWidth,
      height: container.scrollHeight,
    });

    const newConnections: Connection[] = [];
    for (const conn of connectionDefs) {
      const fromEl = nodeRefs.current.get(conn.from);
      const toEl = nodeRefs.current.get(conn.to);
      if (!fromEl || !toEl) continue;

      const fromRect = fromEl.getBoundingClientRect();
      const toRect = toEl.getBoundingClientRect();

      const startX = fromRect.right - containerRect.left + scrollLeft - 2;
      const startY = fromRect.top + fromRect.height / 2 - containerRect.top + scrollTop;
      const endX = toRect.left - containerRect.left + scrollLeft + 2;
      const endY = toRect.top + toRect.height / 2 - containerRect.top + scrollTop;

      const dx = endX - startX;
      const cp1x = startX + dx * 0.4;
      const cp2x = endX - dx * 0.4;

      newConnections.push({
        from: conn.from,
        to: conn.to,
        color: conn.color,
        path: `M ${startX} ${startY} C ${cp1x} ${startY}, ${cp2x} ${endY}, ${endX} ${endY}`,
        animDur: 2 + Math.random() * 2,
        animBegin: Math.random() * 3,
      });
    }
    setConnections(newConnections);
  }, [connectionDefs]);

  useEffect(() => {
    // Draw after initial render
    const timer = setTimeout(drawConnections, 100);
    window.addEventListener("resize", drawConnections);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", drawConnections);
    };
  }, [drawConnections]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveNode(null);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  const handleNodeClick = (id: string) => {
    setActiveNode((prev) => (prev === id ? null : id));
  };

  const getConnectionOpacity = (conn: Connection) => {
    if (!highlightedId) return 0.25;
    if (conn.from === highlightedId || conn.to === highlightedId) return 0.7;
    return 0.06;
  };

  const getConnectionStroke = (conn: Connection) => {
    if (!highlightedId) return 1.5;
    if (conn.from === highlightedId || conn.to === highlightedId) return 2.5;
    return 1.5;
  };

  const getNodeOpacity = (nodeId: string) => {
    if (!highlightedId) return 1;
    if (nodeId === highlightedId || connectedNodes?.has(nodeId)) return 1;
    return 0.3;
  };

  const detail: DetailData | null = activeNode ? details[activeNode] ?? null : null;

  return (
    <div className="relative h-full flex flex-col">
      {/* Column Headers - sticky */}
      <div
        className="sticky top-0 z-10 grid items-center gap-6 px-10 py-3 border-b border-[var(--surface-light)] bg-[var(--background)]"
        style={{ gridTemplateColumns: "180px 180px 190px 190px 200px 200px 180px" }}
      >
        {layers.map((layer) => (
          <div
            key={layer.id}
            className="text-[10px] font-medium uppercase tracking-[2px] font-mono text-center"
            style={{ color: layer.color }}
          >
            {layer.label}
          </div>
        ))}
      </div>

      {/* Scrollable content */}
      <div ref={containerRef} className="flex-1 overflow-auto relative">
        {/* SVG Connections */}
        <svg
          className="absolute inset-0 pointer-events-none"
          width={svgSize.width}
          height={svgSize.height}
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          {connections.map((conn, i) => (
            <g key={i}>
              <path
                d={conn.path}
                stroke={conn.color}
                fill="none"
                strokeWidth={getConnectionStroke(conn)}
                opacity={getConnectionOpacity(conn)}
                className="transition-all duration-300"
              />
              {(conn.from === highlightedId || conn.to === highlightedId) && (
                <circle r={2.5} fill={conn.color} opacity={0.9}>
                  <animateMotion
                    dur={`${conn.animDur}s`}
                    repeatCount="indefinite"
                    begin={`${conn.animBegin}s`}
                    path={conn.path}
                  />
                </circle>
              )}
            </g>
          ))}
        </svg>

        {/* Flow Grid */}
        <div
          className="relative z-[2] grid gap-6 px-10 py-6"
          style={{ gridTemplateColumns: "180px 180px 190px 190px 200px 200px 180px" }}
        >
          {layers.map((layer) => (
            <div key={layer.id} className="flex flex-col justify-center gap-3">
              {layer.nodes.map((node) => (
                <div
                  key={node.id}
                  ref={(el) => {
                    if (el) nodeRefs.current.set(node.id, el);
                  }}
                  className={`relative rounded-lg p-3.5 pb-3 cursor-pointer transition-all duration-250 overflow-hidden bg-[var(--surface)] border ${
                    activeNode === node.id
                      ? "border-blue-500 shadow-[0_0_0_1px_#3b82f6,0_8px_32px_rgba(59,130,246,0.15)]"
                      : "border-[var(--surface-light)] hover:border-blue-500 hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.3)]"
                  }`}
                  style={{ opacity: getNodeOpacity(node.id) }}
                  onClick={() => handleNodeClick(node.id)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                >
                  {/* Top accent line */}
                  <div
                    className="absolute top-0 inset-x-0 h-0.5 rounded-t-lg opacity-70"
                    style={{ background: layer.color }}
                  />
                  <span className="text-lg mb-2 block" style={{ filter: "grayscale(0.2)" }}>
                    {node.icon}
                  </span>
                  <div className="font-semibold text-[13px] text-[var(--text-primary)] mb-1 leading-tight">
                    {node.title}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] leading-relaxed font-light">
                    {node.desc}
                  </div>
                  {node.badge && (
                    <span
                      className="inline-block font-mono text-[9px] font-medium px-1.5 py-0.5 rounded mt-2 border"
                      style={{
                        background: layer.badgeColors.bg,
                        color: layer.badgeColors.text,
                        borderColor: layer.badgeColors.border,
                      }}
                    >
                      {node.badge}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Platform Features */}
        <div className="px-10 pt-4 pb-6 max-w-[1340px]">
          <h2
            className="text-[10px] font-medium uppercase tracking-[2px] font-mono mb-4 pb-2 border-b border-[var(--surface-light)]"
            style={{ color: "#94a3b8" }}
          >
            <span className="opacity-40 me-1.5">✦</span>
            {t("dataFlow.platformFeatures")}
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {platformFeatures.map((f, i) => (
              <div
                key={i}
                className="rounded-lg p-4 border border-[var(--surface-light)] bg-[var(--surface)]"
              >
                <div className="flex items-center gap-2.5 mb-2.5">
                  <span className="text-lg">{f.icon}</span>
                  <h3 className="font-semibold text-[13px] text-[var(--text-primary)]">{f.title}</h3>
                </div>
                <p className="text-[11px] text-[var(--text-muted)] leading-relaxed font-light mb-3">{f.desc}</p>
                <ul className="list-none p-0 m-0">
                  {f.highlights.map((h, j) => (
                    <li
                      key={j}
                      className="text-[11px] leading-relaxed text-[var(--text-primary)] font-light before:content-['→_'] before:text-slate-500 before:font-medium"
                    >
                      {h}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* Key Insights */}
        <div className="flex flex-col gap-4 px-10 pb-20 max-w-[1340px]">
          {callouts.map((c, i) => (
            <div
              key={i}
              className="flex gap-3 items-start p-4 rounded-lg border"
              style={{
                background: "linear-gradient(135deg, rgba(251,191,36,0.04), rgba(251,191,36,0.01))",
                borderColor: "rgba(251,191,36,0.15)",
              }}
            >
              <span className="text-base shrink-0 mt-px">{c.icon}</span>
              <p className="text-xs leading-relaxed text-[var(--text-primary)] font-light">
                <strong className="text-amber-400 font-medium">{c.title}</strong> {c.text}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Detail Panel */}
      <div
        className={`fixed bottom-0 inset-x-0 z-[200] bg-[var(--surface)] border-t border-[var(--surface-light)] max-h-[50vh] overflow-y-auto transition-transform duration-350 ${
          detail ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)" }}
      >
        {detail && (
          <div className="p-7 ps-10 max-w-[1100px]">
            {/* Header */}
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">{detail.title}</h2>
              <span className="font-mono text-[10px] px-2 py-0.5 rounded border bg-blue-500/10 text-blue-400 border-blue-500/20">
                {detail.tag}
              </span>
              <button
                onClick={() => setActiveNode(null)}
                className="ms-auto w-7 h-7 rounded-md border border-[var(--surface-light)] text-[var(--text-muted)] hover:border-[var(--text-muted)] hover:text-[var(--text-primary)] transition-all flex items-center justify-center"
              >
                <X size={14} />
              </button>
            </div>
            {/* Body */}
            <div className="grid grid-cols-2 gap-6">
              {detail.sections.map((s, i) => (
                <div key={i}>
                  <h3 className="font-mono text-[10px] font-medium uppercase tracking-[1.5px] text-[var(--text-muted)] mb-2.5">
                    {s.heading}
                  </h3>
                  {s.text && (
                    <p className="text-[13px] leading-relaxed text-[var(--text-primary)] font-light">
                      {s.text}
                    </p>
                  )}
                  {s.items && (
                    <ul className="list-none p-0">
                      {s.items.map((item, j) => (
                        <li
                          key={j}
                          className="text-[13px] leading-relaxed text-[var(--text-primary)] font-light before:content-['\2192_'] before:text-blue-500 before:font-medium"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                  {s.flow && (
                    <div className="flex items-center gap-2 flex-wrap mt-1">
                      {s.flow.map((step, j) => (
                        <span key={j} className="contents">
                          {j > 0 && (
                            <span className="text-[var(--text-muted)] text-xs">{"\u2192"}</span>
                          )}
                          <span className="font-mono text-[11px] px-2.5 py-1 rounded bg-[var(--surface)] border border-[var(--surface-light)] text-[var(--text-primary)]">
                            {step}
                          </span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
