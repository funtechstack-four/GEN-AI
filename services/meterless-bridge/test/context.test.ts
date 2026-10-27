import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createEngines, recordEvidence } from "../src/context.ts";

test("confirmed evidence enters both engines and identical replay is idempotent", async () => {
  const directory = mkdtempSync(path.join(os.tmpdir(), "meterless-context-"));
  try {
    const claims = ["2024-10-04:12679", "2024-05-17:5885", "2023-03-01:100"].map((source_id, index) => ({
      claim_id: `c${index + 1}`,
      kind: "lost_title",
      parcel_id: "N/Wanga/Matungu/954",
      source_id,
      source_type: "gazette",
      status: "confirmed",
      parties: ["A Shared Person"],
    }));
    const parcel = claims[0].parcel_id;
    const firstEngines = createEngines(directory);
    const first = await recordEvidence(firstEngines, "run-1", parcel, claims);
    assert.equal(first.world.source_count, 3);
    assert.ok(first.world.events_appended > 0);
    assert.ok(first.memory.source_ids.includes(claims[0].source_id));
    assert.ok(first.memory.party_patterns.some((pattern) => pattern.notice_count === 3));

    const reloadedEngines = createEngines(directory);
    const replay = await recordEvidence(reloadedEngines, "run-2", parcel, claims);
    assert.equal(replay.world.events_appended, 0);
    assert.equal(reloadedEngines.hmem.store.all().length, 3);
    assert.ok(replay.memory.source_ids.includes(claims[0].source_id));
    assert.ok(replay.memory.party_patterns.some((pattern) => pattern.notice_count === 3));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
