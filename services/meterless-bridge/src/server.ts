import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createEngines, recordEvidence } from "./context.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const dataDir = path.resolve(process.env.METERLESS_DATA_DIR ?? path.join(root, ".state", "meterless"));
const engines = createEngines(dataDir);
const port = Number(process.env.METERLESS_BRIDGE_PORT ?? 4001);
const host = process.env.METERLESS_BRIDGE_HOST ?? "127.0.0.1";
const maxBytes = 1_000_000;

function send(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  res.end(JSON.stringify(payload));
}

async function bodyJson(req: IncomingMessage): Promise<any> {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk.toString();
    if (raw.length > maxBytes) throw new Error("request body too large");
  }
  return JSON.parse(raw || "{}");
}

const server = createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") {
      return send(res, 200, { status: "ok", engines: ["world-model", "hmem"] });
    }
    if (req.method !== "POST" || req.url !== "/context") {
      return send(res, 404, { error: "not_found" });
    }
    const input = await bodyJson(req);
    if (typeof input.run_id !== "string" || typeof input.parcel !== "string" || !Array.isArray(input.claims)) {
      return send(res, 400, { error: "invalid_request" });
    }
    const result = await recordEvidence(engines, input.run_id, input.parcel, input.claims);
    return send(res, 200, result);
  } catch (error) {
    const status = error instanceof SyntaxError ? 400 : 500;
    return send(res, status, { error: status === 400 ? "invalid_json" : "meterless_processing_failed" });
  }
});

server.listen(port, host, () => {
  console.log(`Meterless bridge listening on http://${host}:${port}`);
});
