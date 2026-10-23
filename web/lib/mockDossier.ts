// A stand-in for the real agent while the backend isn't ready.
// It only knows the three demo shapes. Nothing here is a real check.
import type { Dossier, IntakeRequest } from "./contracts";

const CANCELLED_FROM = 5253001;
const CANCELLED_TO = 5253367;

// Always listed when nothing was confirmed (master plan §1.1).
export const REMAINING_CHECKS = [
  "Official search at the Lands Registry (Ardhisasa)",
  "Seller's ID matched against the registered owner",
  "Physical visit and beacon survey",
  "Advocate review before any payment",
];

function runId() {
  return "mock-" + Math.random().toString(36).slice(2, 10);
}

export function isCancelledSerial(serial: string): boolean {
  const n = Number(serial.trim());
  return Number.isInteger(n) && n >= CANCELLED_FROM && n <= CANCELLED_TO;
}

export function mockDossier(req: IntakeRequest): Dossier {
  const base = {
    run_id: runId(),
    parcel_input: req.parcel_input,
    unverified: [],
    objection_windows: [],
    advocate_review: [],
  };

  // Case 1: title paper serial is in the cancelled range -> STOP straight away
  if (isCancelledSerial(req.title_serial)) {
    return {
      ...base,
      verdict: "STOP",
      timeline: [{
        claim_id: "c1",
        kind: "serial_cancelled",
        parcel_id: req.parcel_input,
        // same quote and source as data/extracts/cancelled_serials.csv
        quote: "5253001--5253367",
        source_type: "serial_list",
        source_id: "Gazette Notice 12436, Vol. CXXVI No. 147, 27 Sep 2024 (Loss of title deeds: reported lost, deemed cancelled)",
        status: "confirmed",
        reject_reason: null,
      }],
      remaining_checks: REMAINING_CHECKS,
    };
  }

  // Case 2: the demo HIGH RISK parcel (placeholder until P4 anchors a real one)
  if (req.parcel_input.replace(/\s/g, "").toUpperCase().includes("12715/288")) {
    return {
      ...base,
      verdict: "HIGH RISK",
      timeline: [{
        claim_id: "c1",
        kind: "succession",
        parcel_id: "LR 12715/288",
        quote: "[placeholder quote — replaced by a real Gazette notice on Sat 24 Oct]",
        source_type: "gazette",
        source_id: "Gazette <issue>/<notice no.> (placeholder)",
        status: "confirmed",
        reject_reason: null,
      }],
      unverified: [{
        claim_id: "c2",
        kind: "dispute",
        parcel_id: "LR 12715/289",
        quote: "[placeholder: a notice about the neighbouring parcel]",
        source_type: "gazette",
        source_id: "Gazette <issue>/<notice no.> (placeholder)",
        status: "rejected",
        reject_reason: "Parcel number is 12715/289, not 12715/288",
      }],
      objection_windows: [{ notice_id: "placeholder", closes_on: "2026-11-30", open: true }],
      remaining_checks: REMAINING_CHECKS,
      advocate_review: ["Confirm who holds the grant of letters of administration"],
    };
  }

  // Case 3: nothing found -> VERIFY FIRST (never a "no risk" verdict)
  return { ...base, verdict: "VERIFY FIRST", timeline: [], remaining_checks: REMAINING_CHECKS };
}
