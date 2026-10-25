// Small display helpers for the dossier page. Nothing here changes what was found.
import type { ObjectionWindow } from "./contracts";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2024-12-03" -> "3 Dec 2024". Anything that isn't an ISO date is returned as is. */
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

/** Whole days from a to b (both ISO dates). Negative if b is before a. */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** "2024-10-04:12679" -> "Gazette Notice 12679 (4 Oct 2024)". */
export function noticeLabel(id: string): string {
  const m = /^(\d{4}-\d{2}-\d{2}):(\d+)/.exec(id);
  return m ? `Gazette Notice ${m[2]} (${formatDate(m[1])})` : id;
}

// National ID numbers ("ID/12345678", "ID No. 12345678") and land registrar numbers
// ("MR/6529572") appear in Gazette text. The quote stays verbatim in the data; we only
// hide the digits on screen and in the demo video.
// also catches "ID23394497", "ID 0465403" and 4-digit "MR/4242" (checked on the whole extract)
const ID_RE = /\b(ID|MR)(\s*\/\s*|\.?\s*No\.?\s*|\s*)(\d[\d/]{3,})/gi;

export function maskIds(text: string): string {
  return text.replace(ID_RE, (_all, kind: string, sep: string, digits: string) =>
    `${kind}${sep}${"•".repeat(digits.length)}`);
}

export function hasIds(text: string): boolean {
  ID_RE.lastIndex = 0;
  const found = ID_RE.test(text);
  ID_RE.lastIndex = 0;
  return found;
}

export interface WindowView {
  status: "open" | "closed" | "later";
  chip: string;     // short label, about the sale date
  headline: string; // about the sale date
  detail: string;   // about today
}

/** How to describe one objection window. `open` from the API is about the sale date. */
export function describeWindow(w: ObjectionWindow, today: string, saleDate?: string): WindowView {
  const closes = formatDate(w.closes_on);
  const published = /^\d{4}-\d{2}-\d{2}/.exec(w.notice_id)?.[0];
  const left = daysBetween(today, w.closes_on);
  const detail = left > 1 ? `Window closes on ${closes}, ${left} days from today`
    : left === 1 ? `Window closes tomorrow, ${closes}`
    : left === 0 ? `Window closes today, ${closes}`
    : `Window closed on ${closes}`;
  if (saleDate && published && daysBetween(saleDate, published) > 0) {
    return { status: "later", chip: "After sale", detail,
             headline: `Published after your sale date (${formatDate(saleDate)})` };
  }
  if (!saleDate) {
    return { status: w.open ? "open" : "closed", chip: w.open ? "Open" : "Closed", detail,
             headline: w.open ? "Open" : "Closed" };
  }
  return w.open
    ? { status: "open", chip: "Open at sale", detail, headline: `Still open on your sale date (${formatDate(saleDate)})` }
    : { status: "closed", chip: "Closed at sale", detail, headline: `Closed before your sale date (${formatDate(saleDate)})` };
}
