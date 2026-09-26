import { describe, it, expect } from "vitest";
import {
  buildLayers,
  buildPlatformFeatures,
  buildCallouts,
  connectionDefs,
} from "./dataFlowData";
import enContent from "./dataFlowContent.en";
import heContent from "./dataFlowContent.he";
import type { DataFlowContent } from "./dataFlowData";

/**
 * The Data Flow page is assembled from three files that have to agree:
 * `dataFlowData.ts` holds the structure (which nodes exist, what connects to
 * what, which icon goes with which feature card) and the two content files
 * hold every translatable string.
 *
 * Nothing at runtime complains when they drift. `buildLayers` falls back to
 * `content.nodes[id]?.title ?? id`, so a node added to the structure but not
 * to a locale renders its raw id ("savings-goals-mgmt") as a card title;
 * `details[activeNode] ?? null` leaves the detail panel refusing to open;
 * a connection naming a node that no longer exists is skipped silently; and
 * `platformFeatureIcons[i] ?? ""` gives a feature card an empty icon slot.
 *
 * All four are invisible in a type-check and invisible in a build. So they
 * are asserted here instead.
 */

const LOCALES: Array<[string, DataFlowContent]> = [
  ["en", enContent],
  ["he", heContent],
];

const nodeIds = buildLayers(enContent).flatMap((layer) => layer.nodes.map((n) => n.id));

describe("data flow content", () => {
  it("gives every diagram node a title and description in both locales", () => {
    for (const [lang, content] of LOCALES) {
      const missing = nodeIds.filter((id) => !content.nodes[id]?.title || !content.nodes[id]?.desc);
      expect(missing, `${lang}: nodes without label/description`).toEqual([]);
    }
  });

  it("gives every diagram node a detail panel in both locales", () => {
    for (const [lang, content] of LOCALES) {
      const missing = nodeIds.filter((id) => !content.details[id]);
      expect(missing, `${lang}: nodes whose detail panel would not open`).toEqual([]);
    }
  });

  it("keeps every detail panel attached to a node that is on the diagram", () => {
    const known = new Set(nodeIds);
    for (const [lang, content] of LOCALES) {
      const orphans = Object.keys(content.details).filter((id) => !known.has(id));
      expect(orphans, `${lang}: detail panels no node can open`).toEqual([]);
    }
  });

  it("gives every layer a label in both locales", () => {
    const layerIds = buildLayers(enContent).map((l) => l.id);
    for (const [lang, content] of LOCALES) {
      const missing = layerIds.filter((id) => !content.layerLabels[id]);
      expect(missing, `${lang}: column headers falling back to their id`).toEqual([]);
    }
  });

  it("only draws connections between nodes that exist", () => {
    const known = new Set(nodeIds);
    const dangling = connectionDefs
      .filter((c) => !known.has(c.from) || !known.has(c.to))
      .map((c) => `${c.from} -> ${c.to}`);
    expect(dangling, "connections silently dropped at render time").toEqual([]);
  });

  it("leaves no node stranded without a connection", () => {
    const connected = new Set(connectionDefs.flatMap((c) => [c.from, c.to]));
    const stranded = nodeIds.filter((id) => !connected.has(id));
    expect(stranded, "nodes with no edge in or out").toEqual([]);
  });

  it("gives every feature card and callout an icon in both locales", () => {
    for (const [lang, content] of LOCALES) {
      const features = buildPlatformFeatures(content);
      expect(features.length, `${lang}: feature cards`).toBe(enContent.platformFeatures.length);
      expect(
        features.filter((f) => !f.icon).map((f) => f.title),
        `${lang}: feature cards with an empty icon slot`,
      ).toEqual([]);

      const callouts = buildCallouts(content);
      expect(callouts.length, `${lang}: callouts`).toBe(enContent.callouts.length);
      expect(
        callouts.filter((c) => !c.icon).map((c) => c.title),
        `${lang}: callouts with an empty icon slot`,
      ).toEqual([]);
    }
  });

  it("keeps the Hebrew translation in step with the English source", () => {
    expect(Object.keys(heContent.nodes).sort()).toEqual(Object.keys(enContent.nodes).sort());
    expect(Object.keys(heContent.details).sort()).toEqual(Object.keys(enContent.details).sort());
    expect(heContent.platformFeatures.length).toBe(enContent.platformFeatures.length);
    expect(heContent.callouts.length).toBe(enContent.callouts.length);
  });
});
