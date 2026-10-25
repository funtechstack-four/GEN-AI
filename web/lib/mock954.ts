// Mock for the real demo parcel N/Wanga/Matungu/954 (eval cases 1b and 2), so the
// objection windows can be shown before the backend exists. Quotes are copied word for
// word from the notices' raw_text in data/extracts/gazette_notices.parquet.
import type { Claim, Dossier, IntakeRequest, ObjectionWindow } from "./contracts";
import { daysBetween } from "./format";

const PARCEL = "N/WANGA/MATUNGU/954";

export function is954(input: string): boolean {
  return input.toUpperCase().replace(/\s/g, "") === PARCEL;
}

interface Notice {
  id: string;
  kind: Claim["kind"];
  quote: string;
  closes_on: string; // issue_date + objection_days, moved off Sundays (docs/objection-windows.md)
}

const NOTICES: Notice[] = [
  {
    id: "2024-05-17:5885", kind: "lost_title", closes_on: "2024-07-16",
    quote: "registered under title No. N/Wanga/Matungu/954, and whereas sufficient evidence has been "
      + "adduced to show that the land title deed issued thereof has been lost",
  },
  {
    id: "2024-06-21:7770", kind: "succession", closes_on: "2024-07-22", // day 30 is a Sunday
    quote: "whereas the Kakamega Court in Succession Cause No. E102 of 2021 has issued grant of letters "
      + "of administration",
  },
  {
    id: "2024-10-04:12679", kind: "lost_title", closes_on: "2024-12-03",
    quote: "registered under title No. N/Wanga/Matungu/954, and whereas sufficient evidence has been "
      + "adduced to show that the land title deed issued thereof has been lost",
  },
  {
    id: "2024-10-04:12777", kind: "succession", closes_on: "2024-11-04", // day 30 is a Sunday
    quote: "whereas the Court in Succession Cause No. E102 of 2021, has issued grant of letters of "
      + "administration",
  },
];

export function mock954(req: IntakeRequest, base: Omit<Dossier, "verdict" | "timeline" | "remaining_checks">,
                        remaining: string[]): Dossier {
  const sale = req.sale_date;
  const timeline: Claim[] = NOTICES.map((n, i) => ({
    claim_id: `c${i + 1}`, kind: n.kind, parcel_id: "N/Wanga/Matungu/954", quote: n.quote,
    source_type: "gazette", source_id: n.id, status: "confirmed", reject_reason: null,
  }));
  const windows: ObjectionWindow[] = NOTICES.map((n) => ({
    // open on the sale date = published on or before it, and not closed yet
    notice_id: n.id, closes_on: n.closes_on,
    open: daysBetween(n.id.slice(0, 10), sale) >= 0 && daysBetween(sale, n.closes_on) >= 0,
  }));
  // STOP if a lost-title notice is dated within the 12 months before the sale (plan §1.1)
  const recentLoss = NOTICES.some((n) => {
    if (n.kind !== "lost_title") return false;
    const age = daysBetween(n.id.slice(0, 10), sale);
    return age >= 0 && age <= 365;
  });
  return {
    ...base,
    verdict: recentLoss ? "STOP" : "HIGH RISK",
    timeline,
    objection_windows: windows,
    remaining_checks: remaining,
    advocate_review: [
      "Two lost-title notices for this parcel in the same year (May and October 2024)",
      "Confirm the succession (Cause No. E102 of 2021) is complete and who can sell",
    ],
  };
}
