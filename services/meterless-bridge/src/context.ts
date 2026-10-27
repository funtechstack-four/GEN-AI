import { mkdirSync } from "node:fs";
import path from "node:path";
import { HMEM } from "../../../vendor/meterless/hmem/reference/src/index.ts";
import { WorldModel } from "../../../vendor/meterless/world-model/reference/src/index.ts";

export type ConfirmedClaim = {
  claim_id: string;
  kind: string;
  parcel_id: string;
  source_id: string;
  source_type: string;
  status: string;
  parties?: string[];
};

export function createEngines(dataDir: string) {
  const worldDir = path.join(dataDir, "world");
  const memoryDir = path.join(dataDir, "hmem");
  mkdirSync(worldDir, { recursive: true });
  mkdirSync(memoryDir, { recursive: true });
  return {
    world: new WorldModel({ namespace: "land-title-due-diligence", storage: "local", directory: worldDir }),
    hmem: new HMEM({ persistDir: memoryDir, actor: "land-title-agent" }),
  };
}

function observationDate(sourceId: string): string {
  const value = sourceId.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00.000Z` : new Date().toISOString();
}

export async function recordEvidence(
  engines: ReturnType<typeof createEngines>, runId: string, parcel: string, inputClaims: ConfirmedClaim[],
) {
  const claims = inputClaims.filter((claim) => claim?.status === "confirmed").slice(0, 100);
  if (claims.length === 0) return { world: { source_count: 0 }, memory: { source_ids: [], match_count: 0 } };

  const observations = claims.map((claim) => {
    const sourceId = String(claim.source_id ?? "").slice(0, 250);
    const at = observationDate(sourceId);
    return {
      externalId: `${claim.source_type}:${sourceId}`,
      type: "land_record",
      title: `${claim.kind} evidence for ${parcel}`,
      text: `Confirmed source record ${sourceId} for parcel ${parcel}`,
      at,
      source: { kind: "agent", by: "evidence-critic", at, runId },
      entities: [
        { type: "parcel", name: parcel },
        { type: "source", name: sourceId },
        ...(claim.parties ?? []).slice(0, 10).map((name) => ({ type: "person", name })),
      ],
    };
  });
  const worldReport = await engines.world.ingest(observations);

  const existing = new Set(engines.hmem.store.all().map((memory) => memory.content));
  for (const claim of claims) {
    const sourceId = String(claim.source_id ?? "").slice(0, 250);
    const parties = (claim.parties ?? []).slice(0, 10);
    const contentItems = parties.length
      ? parties.map((party) => `${claim.kind} record; parcel: ${parcel}; source: ${sourceId}; party: ${party};`)
      : [`${claim.kind} record; parcel: ${parcel}; source: ${sourceId}`];
    for (const content of contentItems) {
      if (existing.has(content)) continue;
      engines.hmem.add({
        content,
        type: "factual",
        layer: "long_term",
        tags: ["land-title", claim.kind],
        confidence: 1,
        source: sourceId,
        provenance: { origin: "document", learnedAt: Date.now(), label: "Evidence Critic confirmed source", refs: [sourceId] },
      });
      existing.add(content);
    }
  }
  const recalled = engines.hmem.query(`land title parcel ${parcel}`, { topN: 5, threshold: 0.25 });
  const sourceIds = [...new Set(recalled.memories.flatMap(({ memory }) => {
    const found = memory.content.match(/source: ([^;]+)/);
    return found ? [found[1]] : [];
  }))].slice(0, 10);
  const patterns = new Map<string, Set<string>>();
  for (const party of new Set(claims.flatMap((claim) => claim.parties ?? []))) {
    const retrieved = engines.hmem.query(`lost_title party ${party}`, { topN: 20, threshold: 0 });
    for (const { memory } of retrieved.memories) {
      if (!memory.content.toLocaleLowerCase().includes(`party: ${party.toLocaleLowerCase()};`)) continue;
      if (!memory.content.startsWith("lost_title record;")) continue;
      const found = memory.content.match(/source: ([^;]+)/);
      if (!found) continue;
      const refs = patterns.get(party) ?? new Set<string>();
      refs.add(found[1]);
      patterns.set(party, refs);
    }
  }
  const partyPatterns = [...patterns.values()]
    .filter((refs) => refs.size >= 3)
    .map((refs) => ({ notice_count: refs.size, source_ids: [...refs].sort().slice(0, 10) }));
  return {
    world: { source_count: claims.length, events_appended: worldReport.eventsAppended },
    memory: {
      source_ids: sourceIds,
      match_count: recalled.memories.length,
      retrieval_reason: recalled.trace.retrievalReason,
      party_patterns: partyPatterns,
    },
  };
}
