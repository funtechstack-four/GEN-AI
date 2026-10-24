// Talks to the FastAPI backend (agents/api.py). Falls back to the mock
// when the backend isn't running yet, and says so on the page.
import type { Dossier, IntakeRequest } from "./contracts";
import { mockDossier } from "./mockDossier";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function requestDossier(
  req: IntakeRequest,
): Promise<{ dossier: Dossier; fromMock: boolean }> {
  try {
    const res = await fetch(`${API_URL}/dossier`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
      signal: AbortSignal.timeout(120_000), // a full run should finish in minutes
    });
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    return { dossier: (await res.json()) as Dossier, fromMock: false };
  } catch {
    return { dossier: mockDossier(req), fromMock: true };
  }
}
