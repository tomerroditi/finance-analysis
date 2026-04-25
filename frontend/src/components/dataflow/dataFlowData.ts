/* ------------------------------------------------------------------ */
/*  Interfaces                                                         */
/* ------------------------------------------------------------------ */

export interface NodeData {
  id: string;
  icon: string;
  title: string;
  desc: string;
  badge?: string;
}

export interface LayerData {
  id: string;
  label: string;
  color: string;
  badgeColors: { bg: string; text: string; border: string };
  nodes: NodeData[];
}

export interface ConnectionDef {
  from: string;
  to: string;
  color: string;
}

export interface DetailSection {
  heading: string;
  text?: string;
  items?: string[];
  flow?: string[];
}

export interface DetailData {
  title: string;
  tag: string;
  sections: DetailSection[];
}

export interface PlatformFeature {
  icon: string;
  title: string;
  desc: string;
  highlights: string[];
}

export interface Callout {
  icon: string;
  title: string;
  text: string;
}

/* ------------------------------------------------------------------ */
/*  Content interface — everything that varies by language              */
/* ------------------------------------------------------------------ */

export interface NodeContent {
  title: string;
  desc: string;
}

export interface DataFlowContent {
  layerLabels: Record<string, string>;
  nodes: Record<string, NodeContent>;
  details: Record<string, DetailData>;
  platformFeatures: Array<{ title: string; desc: string; highlights: string[] }>;
  callouts: Array<{ title: string; text: string }>;
}

/* ------------------------------------------------------------------ */
/*  Structural data — shared across languages                          */
/* ------------------------------------------------------------------ */

interface LayerStructure {
  id: string;
  color: string;
  badgeColors: { bg: string; text: string; border: string };
  nodes: Array<{ id: string; icon: string; badge?: string }>;
}

const layerStructure: LayerStructure[] = [
  {
    id: "sources",
    color: "#22d3ee",
    badgeColors: { bg: "rgba(34,211,238,0.1)", text: "#22d3ee", border: "rgba(34,211,238,0.2)" },
    nodes: [
      { id: "banks", icon: "\u{1F3E6}", badge: "PLAYWRIGHT" },
      { id: "credit-cards", icon: "\u{1F4B3}", badge: "PLAYWRIGHT" },
      { id: "insurance", icon: "\u{1F6E1}\uFE0F", badge: "PLAYWRIGHT" },
      { id: "manual", icon: "\u270F\uFE0F", badge: "UI FORMS" },
    ],
  },
  {
    id: "ingestion",
    color: "#3b82f6",
    badgeColors: { bg: "rgba(59,130,246,0.1)", text: "#3b82f6", border: "rgba(59,130,246,0.2)" },
    nodes: [
      { id: "scraper", icon: "\u{1F577}\uFE0F", badge: "ASYNC" },
      { id: "adapter", icon: "\u{1F50C}", badge: "BRIDGE" },
      { id: "api-routes", icon: "\u{1F310}", badge: "FASTAPI" },
    ],
  },
  {
    id: "processing",
    color: "#fbbf24",
    badgeColors: { bg: "rgba(251,191,36,0.1)", text: "#fbbf24", border: "rgba(251,191,36,0.2)" },
    nodes: [
      { id: "auto-tag", icon: "\u{1F3F7}\uFE0F", badge: "RULES ENGINE" },
      { id: "balance-recalc", icon: "\u2696\uFE0F" },
      { id: "prior-wealth", icon: "\u{1F3DB}\uFE0F", badge: "SYNTHETIC ROWS" },
    ],
  },
  {
    id: "storage",
    color: "#34d399",
    badgeColors: { bg: "rgba(52,211,153,0.1)", text: "#34d399", border: "rgba(52,211,153,0.2)" },
    nodes: [
      { id: "txn-tables", icon: "\u{1F4CB}", badge: "5 TABLES" },
      { id: "bank-bal", icon: "\u{1F3E6}" },
      { id: "cash-bal", icon: "\u{1F4B5}" },
      { id: "inv-snapshots", icon: "\u{1F4F8}", badge: "SNAPSHOT-FIRST" },
      { id: "meta-tables", icon: "\u2699\uFE0F" },
      { id: "demo-mode", icon: "\uD83E\uddEA", badge: "TOGGLE" },
      { id: "backup", icon: "\uD83D\uDCBE", badge: "SNAPSHOTS" },
    ],
  },
  {
    id: "management",
    color: "#fb923c",
    badgeColors: { bg: "rgba(251,146,60,0.1)", text: "#fb923c", border: "rgba(251,146,60,0.2)" },
    nodes: [
      { id: "manual-tagging", icon: "\u{1F3F7}\uFE0F", badge: "USER-DRIVEN" },
      { id: "splits", icon: "\u2702\uFE0F" },
      { id: "cc-dedup", icon: "\u{1F500}", badge: "CRITICAL" },
      { id: "refunds-mgmt", icon: "\u{1F4B8}", badge: "BUDGET ADJUST" },
      { id: "invest-mgmt", icon: "\u{1F4BC}" },
      { id: "liab-mgmt", icon: "\u{1F4DD}" },
      { id: "budget-mgmt", icon: "\u{1F4CA}", badge: "RULES + PROJECTS" },
      { id: "balance-mgmt", icon: "\u{1F4B1}", badge: "TRIGGERS PRIOR WEALTH" },
      { id: "cat-mgmt", icon: "\u{1F4C1}", badge: "CASCADE" },
    ],
  },
  {
    id: "analytics",
    color: "#a78bfa",
    badgeColors: { bg: "rgba(167,139,250,0.1)", text: "#a78bfa", border: "rgba(167,139,250,0.2)" },
    nodes: [
      { id: "analysis-svc", icon: "\u{1F4CA}", badge: "7 KPI METHODS" },
      { id: "budget-svc", icon: "\u{1F3AF}" },
      { id: "invest-svc", icon: "\u{1F4C8}" },
      { id: "liab-svc", icon: "\u{1F4C9}" },
      { id: "retire-svc", icon: "\u{1F3D6}\uFE0F" },
    ],
  },
  {
    id: "frontend",
    color: "#f472b6",
    badgeColors: { bg: "rgba(244,114,182,0.1)", text: "#f472b6", border: "rgba(244,114,182,0.2)" },
    nodes: [
      { id: "dashboard", icon: "\u{1F5A5}\uFE0F", badge: "10+ QUERIES" },
      { id: "txn-page", icon: "\u{1F4D1}" },
      { id: "budget-page", icon: "\u{1F4B0}" },
      { id: "categories-page", icon: "\u{1F3F7}\uFE0F" },
      { id: "invest-page", icon: "\u{1F5C2}\uFE0F" },
      { id: "liab-page", icon: "\u{1F3D7}\uFE0F" },
      { id: "insurance-page", icon: "\u{1F6E1}\uFE0F" },
      { id: "retire-page", icon: "\u{1F305}" },
      { id: "datasources-page", icon: "\u{1F4E1}" },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Connections — purely structural, no translatable text               */
/* ------------------------------------------------------------------ */

export const connectionDefs: ConnectionDef[] = [
  // Sources -> Ingestion
  { from: "banks", to: "scraper", color: "#22d3ee" },
  { from: "credit-cards", to: "scraper", color: "#22d3ee" },
  { from: "insurance", to: "scraper", color: "#22d3ee" },
  { from: "manual", to: "api-routes", color: "#22d3ee" },
  // Ingestion -> Processing
  { from: "scraper", to: "adapter", color: "#3b82f6" },
  { from: "adapter", to: "auto-tag", color: "#3b82f6" },
  { from: "adapter", to: "balance-recalc", color: "#3b82f6" },
  // Ingestion -> Storage
  { from: "adapter", to: "txn-tables", color: "#3b82f6" },
  { from: "api-routes", to: "txn-tables", color: "#3b82f6" },
  // Processing -> Storage
  { from: "auto-tag", to: "txn-tables", color: "#fbbf24" },
  { from: "balance-recalc", to: "bank-bal", color: "#fbbf24" },
  { from: "prior-wealth", to: "bank-bal", color: "#fbbf24" },
  { from: "prior-wealth", to: "cash-bal", color: "#fbbf24" },
  { from: "prior-wealth", to: "inv-snapshots", color: "#fbbf24" },
  { from: "api-routes", to: "prior-wealth", color: "#3b82f6" },
  // Storage -> Management
  { from: "txn-tables", to: "manual-tagging", color: "#34d399" },
  { from: "txn-tables", to: "splits", color: "#34d399" },
  { from: "txn-tables", to: "cc-dedup", color: "#34d399" },
  { from: "txn-tables", to: "refunds-mgmt", color: "#34d399" },
  { from: "txn-tables", to: "invest-mgmt", color: "#34d399" },
  { from: "txn-tables", to: "liab-mgmt", color: "#34d399" },
  { from: "meta-tables", to: "cat-mgmt", color: "#34d399" },
  { from: "meta-tables", to: "manual-tagging", color: "#34d399" },
  { from: "inv-snapshots", to: "invest-mgmt", color: "#34d399" },
  // Management -> Storage (writes back)
  { from: "manual-tagging", to: "txn-tables", color: "#fb923c" },
  { from: "splits", to: "txn-tables", color: "#fb923c" },
  { from: "cat-mgmt", to: "meta-tables", color: "#fb923c" },
  { from: "invest-mgmt", to: "inv-snapshots", color: "#fb923c" },
  // Management -> Analytics
  { from: "cc-dedup", to: "analysis-svc", color: "#fb923c" },
  { from: "refunds-mgmt", to: "budget-svc", color: "#fb923c" },
  { from: "invest-mgmt", to: "invest-svc", color: "#fb923c" },
  { from: "liab-mgmt", to: "liab-svc", color: "#fb923c" },
  { from: "splits", to: "analysis-svc", color: "#fb923c" },
  { from: "manual-tagging", to: "analysis-svc", color: "#fb923c" },
  // Management -> Storage (budget & balance writes)
  { from: "budget-mgmt", to: "meta-tables", color: "#fb923c" },
  { from: "balance-mgmt", to: "bank-bal", color: "#fb923c" },
  { from: "balance-mgmt", to: "cash-bal", color: "#fb923c" },
  // Management -> Analytics (budget & balance)
  { from: "budget-mgmt", to: "budget-svc", color: "#fb923c" },
  { from: "balance-mgmt", to: "analysis-svc", color: "#fb923c" },
  // Storage -> Management (budget & balance reads)
  { from: "meta-tables", to: "budget-mgmt", color: "#34d399" },
  { from: "bank-bal", to: "balance-mgmt", color: "#34d399" },
  { from: "cash-bal", to: "balance-mgmt", color: "#34d399" },
  // Storage -> Analytics (direct reads)
  { from: "bank-bal", to: "analysis-svc", color: "#34d399" },
  { from: "cash-bal", to: "analysis-svc", color: "#34d399" },
  { from: "meta-tables", to: "budget-svc", color: "#34d399" },
  // Analytics -> Frontend
  { from: "analysis-svc", to: "dashboard", color: "#a78bfa" },
  { from: "budget-svc", to: "budget-page", color: "#a78bfa" },
  { from: "invest-svc", to: "invest-page", color: "#a78bfa" },
  { from: "liab-svc", to: "liab-page", color: "#a78bfa" },
  { from: "retire-svc", to: "retire-page", color: "#a78bfa" },
  { from: "txn-tables", to: "txn-page", color: "#34d399" },
  { from: "meta-tables", to: "categories-page", color: "#34d399" },
  { from: "txn-tables", to: "insurance-page", color: "#34d399" },
  { from: "meta-tables", to: "datasources-page", color: "#34d399" },
  // Demo Mode connections
  { from: "demo-mode", to: "scraper", color: "#34d399" },
  { from: "demo-mode", to: "txn-tables", color: "#34d399" },
  // Backup connections
  { from: "backup", to: "txn-tables", color: "#34d399" },
  { from: "backup", to: "meta-tables", color: "#34d399" },
];

/* ------------------------------------------------------------------ */
/*  Callout icons — shared across languages                            */
/* ------------------------------------------------------------------ */

const calloutIcons = ["\u26A1", "\u26A1", "\u26A1", "\u26A1", "\u26A1"];

/* ------------------------------------------------------------------ */
/*  Platform feature icons — shared across languages                   */
/* ------------------------------------------------------------------ */

const platformFeatureIcons = ["✂️", "🏷️", "💰", "📈", "💸", "🌐"];

/* ------------------------------------------------------------------ */
/*  Builder — merges structural data with language content              */
/* ------------------------------------------------------------------ */

export function buildLayers(content: DataFlowContent): LayerData[] {
  return layerStructure.map((layer) => ({
    id: layer.id,
    label: content.layerLabels[layer.id] ?? layer.id,
    color: layer.color,
    badgeColors: layer.badgeColors,
    nodes: layer.nodes.map((node) => ({
      id: node.id,
      icon: node.icon,
      badge: node.badge,
      title: content.nodes[node.id]?.title ?? node.id,
      desc: content.nodes[node.id]?.desc ?? "",
    })),
  }));
}

export function buildPlatformFeatures(content: DataFlowContent): PlatformFeature[] {
  return content.platformFeatures.map((f, i) => ({
    icon: platformFeatureIcons[i] ?? "",
    title: f.title,
    desc: f.desc,
    highlights: f.highlights,
  }));
}

export function buildCallouts(content: DataFlowContent): Callout[] {
  return content.callouts.map((c, i) => ({
    icon: calloutIcons[i] ?? "\u26A1",
    title: c.title,
    text: c.text,
  }));
}
