// TypeScript copy of the frozen contracts in agents/contracts.py (master plan §2.2).
// If P2 changes contracts.py, change this file to match. Don't add fields here first.

export type Verdict = "STOP" | "HIGH RISK" | "VERIFY FIRST";

export type ClaimKind =
  | "serial_cancelled" | "lost_title" | "succession" | "dispute"
  | "court_order" | "acquisition" | "transfer";

export type SourceType = "gazette" | "judgment" | "serial_list" | "registry";

export interface Claim {
  claim_id: string;
  kind: ClaimKind;
  parcel_id: string;
  quote: string;               // verbatim substring of the source text
  source_type: SourceType;
  source_id: string;
  status: "pending" | "confirmed" | "rejected" | "unverified";
  reject_reason: string | null;
}

export interface ObjectionWindow {
  notice_id: string;
  closes_on: string;           // ISO date
  open: boolean;
}

export interface Dossier {
  run_id: string;
  parcel_input: string;
  verdict: Verdict;
  timeline: Claim[];           // confirmed only, sorted by date
  unverified: Claim[];
  objection_windows: ObjectionWindow[];
  remaining_checks: string[];
  advocate_review: string[];
}

// What the intake form sends to POST /dossier.
// Not in the frozen contract yet; P2 to confirm the field names.
export interface IntakeRequest {
  parcel_input: string;
  title_serial: string;
  seller_name: string;
  sale_date: string;           // ISO date, defaults to today
}
