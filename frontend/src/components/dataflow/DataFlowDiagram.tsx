import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Maximize2, Minus, Plus, X } from "lucide-react";
import { useDataFlowData } from "./useDataFlowData";
import type { DetailData } from "./dataFlowData";

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 1.5;
const ZOOM_STEP = 0.1;
const DRAG_THRESHOLD_PX = 5;
const roundZoom = (z: number) => Math.round(z * 100) / 100;

interface Connection {
  from: string;
  to: string;
  color: string;
  path: string;
  animDur: number;
  animBegin: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  startScrollLeft: number;
  startScrollTop: number;
  hasDragged: boolean;
}

export function DataFlowDiagram() {
  const { t } = useTranslation();
  const { layers, connectionDefs, details, callouts, platformFeatures } = useDataFlowData();
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const [zoom, setZoom] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const zoomableRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const dragRef = useRef<DragState | null>(null);

  const fitZoomToViewport = useCallback(() => {
    const container = containerRef.current;
    const zoomable = zoomableRef.current;
    if (!container || !zoomable) return 1;
    const intrinsic = zoomable.scrollWidth / zoom;
    const target = container.clientWidth - 8;
    if (intrinsic <= 0) return 1;
    return Math.max(MIN_ZOOM, Math.min(1, roundZoom(target / intrinsic)));
  }, [zoom]);

  const handleZoomIn = () => setZoom((z) => roundZoom(Math.min(MAX_ZOOM, z + ZOOM_STEP)));
  const handleZoomOut = () => setZoom((z) => roundZoom(Math.max(MIN_ZOOM, z - ZOOM_STEP)));
  const handleFit = () => setZoom(fitZoomToViewport());

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
    const zoomable = zoomableRef.current;
    if (!container || !zoomable) return;

    const containerRect = container.getBoundingClientRect();
    const zoomableRect = zoomable.getBoundingClientRect();
    const scrollLeft = container.scrollLeft;
    const scrollTop = container.scrollTop;

    // Size the SVG to the zoomable wrapper's visual dimensions.
    // `scrollWidth/scrollHeight` return the intrinsic (unzoomed) values under
    // CSS `zoom`, so they don't shrink after zooming out — the SVG would
    // stay huge and leave empty scrollable space. getBoundingClientRect,
    // by contrast, returns the visual (scaled) rect, which is what we want.
    setSvgSize({
      width: zoomableRect.width,
      height: zoomableRect.height,
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
    // Draw after initial render; redraw on zoom change.
    const timer = setTimeout(drawConnections, 100);
    window.addEventListener("resize", drawConnections);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", drawConnections);
    };
  }, [drawConnections, zoom]);

  useEffect(() => {
    // Auto-fit once on mount when the intrinsic diagram doesn't fit the viewport.
    const timer = setTimeout(() => {
      const container = containerRef.current;
      const zoomable = zoomableRef.current;
      if (!container || !zoomable) return;
      const intrinsic = zoomable.scrollWidth;
      const target = container.clientWidth - 8;
      if (intrinsic > 0 && intrinsic > target) {
        setZoom(Math.max(MIN_ZOOM, roundZoom(target / intrinsic)));
      }
    }, 120);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveNode(null);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Only drag-to-pan with mouse; touch keeps native overflow scrolling.
    if (e.pointerType !== "mouse") return;
    if (e.button !== 0) return;
    const el = containerRef.current;
    if (!el) return;
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      startScrollLeft: el.scrollLeft,
      startScrollTop: el.scrollTop,
      hasDragged: false,
    };
    setIsDragging(true);
    el.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const el = containerRef.current;
    if (!drag || !el || drag.pointerId !== e.pointerId) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.hasDragged && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
      drag.hasDragged = true;
    }
    el.scrollLeft = drag.startScrollLeft - dx;
    el.scrollTop = drag.startScrollTop - dy;
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const el = containerRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    if (el?.hasPointerCapture(e.pointerId)) {
      el.releasePointerCapture(e.pointerId);
    }
    setIsDragging(false);
    // Keep `hasDragged` on the ref so the click that follows pointerup can
    // bail out on the node; it gets reset on the next pointerdown.
  };

  const handleNodeClick = (id: string) => {
    if (dragRef.current?.hasDragged) return;
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
    <div className="flex flex-col gap-4 md:gap-6">
      {/* Diagram viewport — a bounded box. Zooming and panning happen only
          inside this box; everything outside (page scroll, feature cards
          below) behaves normally. */}
      <div className="relative rounded-lg border border-[var(--surface-light)] bg-[var(--background)] overflow-hidden h-[55vh] md:h-[70vh]">
        <div
          ref={containerRef}
          className={`absolute inset-0 overflow-auto select-none ${
            isDragging ? "cursor-grabbing" : "cursor-grab"
          }`}
          style={{ touchAction: "pan-x pan-y" }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {/* SVG Connections — sibling of the zoom wrapper so paths render in
              the container's unzoomed pixel space (getBoundingClientRect on
              zoomed nodes already returns visual coords). */}
          <svg
            className="absolute inset-0 pointer-events-none z-0"
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

          <div ref={zoomableRef} style={{ zoom }} className="relative z-[1]">
            {/* Column Headers - sticky, scroll horizontally with content.
                `w-max` makes the background span the full grid width so all
                labels stay readable on top of the diagram when scrolled. */}
            <div
              className="sticky top-0 z-10 grid items-center gap-6 px-10 py-3 border-b border-[var(--surface-light)] bg-[var(--background)] w-max"
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
          </div>
        </div>

        {/* Zoom controls */}
        <div className="absolute bottom-3 end-3 z-20 flex items-center gap-0.5 bg-[var(--surface)]/95 backdrop-blur border border-[var(--surface-light)] rounded-lg shadow-lg p-1">
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={zoom <= MIN_ZOOM}
            aria-label={t("dataFlow.zoomOut")}
            title={t("dataFlow.zoomOut")}
            className="w-8 h-8 flex items-center justify-center rounded text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Minus size={16} />
          </button>
          <button
            type="button"
            onClick={handleFit}
            aria-label={t("dataFlow.fitToScreen")}
            title={t("dataFlow.fitToScreen")}
            className="h-8 px-2 flex items-center justify-center gap-1.5 rounded text-[var(--text-primary)] hover:bg-[var(--surface-light)] transition-colors"
          >
            <Maximize2 size={14} />
            <span className="font-mono text-[11px] text-[var(--text-muted)] tabular-nums">
              {Math.round(zoom * 100)}%
            </span>
          </button>
          <button
            type="button"
            onClick={handleZoomIn}
            disabled={zoom >= MAX_ZOOM}
            aria-label={t("dataFlow.zoomIn")}
            title={t("dataFlow.zoomIn")}
            className="w-8 h-8 flex items-center justify-center rounded text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>

      {/* Platform Features */}
      <div>
        <h2
          className="text-[10px] font-medium uppercase tracking-[2px] font-mono mb-4 pb-2 border-b border-[var(--surface-light)]"
          style={{ color: "#94a3b8" }}
        >
          <span className="opacity-40 me-1.5">✦</span>
          {t("dataFlow.platformFeatures")}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {platformFeatures.map((f, i) => (
            <div
              key={i}
              className="rounded-lg p-4 border border-[var(--surface-light)] bg-[var(--surface)]"
            >
              <div className="flex items-center gap-2.5 mb-2.5">
                <span className="text-lg">{f.icon}</span>
                <h3 className="font-semibold text-[13px] text-[var(--text-primary)]">{f.title}</h3>
              </div>
              <p className="text-[11px] text-[var(--text-muted)] leading-relaxed font-light mb-3">
                {f.desc}
              </p>
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
      <div className="flex flex-col gap-4 pb-4">
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

      {/* Detail Panel */}
      <div
        className={`fixed bottom-0 inset-x-0 z-[200] bg-[var(--surface)] border-t border-[var(--surface-light)] max-h-[70vh] md:max-h-[50vh] overflow-y-auto transition-transform duration-350 ${
          detail ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)" }}
      >
        {detail && (
          <div className="p-4 md:p-7 md:ps-10 max-w-[1100px]">
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
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
                            <span className="text-[var(--text-muted)] text-xs">{"→"}</span>
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
