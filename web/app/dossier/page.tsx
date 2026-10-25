"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Claim, Dossier, Verdict } from "@/lib/contracts";
import { describeWindow, formatDate, hasIds, maskIds, noticeLabel } from "@/lib/format";

// Icon + word + colour, so the verdict never depends on colour alone.
const VERDICT_INFO: Record<Verdict, { icon: string; css: string; meaning: string }> = {
  "STOP": {
    icon: "⛔", css: "v-stop",
    meaning: "Don't pay anything. A serious problem was confirmed in public records.",
  },
  "HIGH RISK": {
    icon: "⚠️", css: "v-high",
    meaning: "Confirmed warning signs. Get an advocate to review before going further.",
  },
  "VERIFY FIRST": {
    icon: "🔍", css: "v-verify",
    meaning: "Nothing confirmed in the records we searched. That is not proof the title is genuine.",
  },
};

const KIND_LABEL: Record<Claim["kind"], string> = {
  serial_cancelled: "Cancelled title serial",
  lost_title: "Lost title notice",
  succession: "Succession (inheritance) notice",
  dispute: "Land dispute",
  court_order: "Court order",
  acquisition: "Compulsory acquisition",
  transfer: "Transfer notice",
};

function ClaimItem({ c }: { c: Claim }) {
  return (
    <li className="claim">
      <strong>{KIND_LABEL[c.kind]}</strong> · {c.parcel_id}
      <blockquote>“{maskIds(c.quote)}”</blockquote>
      <small>Source: {c.source_type === "gazette" ? noticeLabel(c.source_id) : maskIds(c.source_id)}</small>
      {c.reject_reason && <small className="reject"> · Not counted: {maskIds(c.reject_reason)}</small>}
    </li>
  );
}

const todayIso = () => new Date().toLocaleDateString("en-CA"); // local date, YYYY-MM-DD

// Let long parcel numbers wrap after a slash instead of in the middle of a number.
function Breakable({ text }: { text: string }) {
  const parts = text.split("/");
  return <>{parts.map((p, i) => <span key={i}>{p}{i < parts.length - 1 && <>/<wbr /></>}</span>)}</>;
}

export default function DossierPage() {
  const [data, setData] = useState<{ dossier: Dossier; fromMock: boolean; saleDate?: string } | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("dossier");
      if (raw) setData(JSON.parse(raw));
    } catch {
      /* storage blocked: show the empty state */
    }
    setLoaded(true);
  }, []);

  if (!loaded) return <main className="container"><p>Loading…</p></main>;
  if (!data) {
    return (
      <main className="container">
        <p>No check has been run yet.</p>
        <Link href="/">Check a plot</Link>
      </main>
    );
  }

  const { dossier: d, fromMock, saleDate } = data;
  const v = VERDICT_INFO[d.verdict];
  const today = todayIso();
  const masked = [...d.timeline, ...d.unverified].some((c) => hasIds(c.quote) || hasIds(c.source_id) || hasIds(c.reject_reason ?? ""))
    || d.advocate_review.some(hasIds);

  return (
    <main className="container">
      <Link href="/">← Check another plot</Link>

      {fromMock && (
        <p className="mock-banner">
          Demo data: the agent backend isn&apos;t connected yet, so this is a mock result.
        </p>
      )}

      <h1 className="parcel-title"><Breakable text={d.parcel_input} /></h1>

      <section className={`verdict ${v.css}`} aria-label="Verdict">
        <span className="verdict-icon" aria-hidden="true">{v.icon}</span>
        <div>
          <div className="verdict-word">{d.verdict}</div>
          <div>{v.meaning}</div>
        </div>
      </section>

      <section>
        <h2>What we found</h2>
        {d.timeline.length === 0
          ? <p>No confirmed flags in the records searched.</p>
          : <ul className="claims">{d.timeline.map((c) => <ClaimItem key={c.claim_id} c={c} />)}</ul>}
      </section>

      {d.objection_windows.length > 0 && (
        <section>
          <h2>Objection windows</h2>
          <p className="fine-tight">
            While a window is open, anyone can still object to the notice. Buying during one
            means buying into whatever the objection turns out to be.
          </p>
          <ul className="windows">
            {d.objection_windows.map((w) => {
              const view = describeWindow(w, today, saleDate);
              return (
                <li key={w.notice_id} className={`window w-${view.status}`}>
                  <span className="window-chip">
                    <span aria-hidden="true">{view.status === "open" ? "⏳" : view.status === "later" ? "📅" : "🔒"}</span>{" "}
                    {view.chip}
                  </span>
                  <div>
                    <strong>{noticeLabel(w.notice_id)}</strong>
                    <div>{view.headline}</div>
                    <small>{view.detail}</small>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="fine-tight">
            Dates are worked out from the Gazette notice and move to the next day if they land
            on a Sunday or public holiday. If the newspaper notice came out first the
            window may close a few days earlier, so the Land Registrar should confirm it.
          </p>
        </section>
      )}

      {d.unverified.length > 0 && (
        <section>
          <h2>Not confirmed (not used for the verdict)</h2>
          <ul className="claims">{d.unverified.map((c) => <ClaimItem key={c.claim_id} c={c} />)}</ul>
        </section>
      )}

      {d.advocate_review.length > 0 && (
        <section>
          <h2>For your advocate to review</h2>
          <ul>{d.advocate_review.map((a) => <li key={a}>{maskIds(a)}</li>)}</ul>
        </section>
      )}

      <section>
        <h2>Checks you still need to do</h2>
        <ol>{d.remaining_checks.map((c) => <li key={c}>{c}</li>)}</ol>
      </section>

      {masked && <p className="fine">ID and registrar numbers from the notices are hidden on this page.</p>}
      <p className="fine">
        {saleDate && <>Checked for a sale on {formatDate(saleDate)} · </>}Run ID: {d.run_id}
      </p>
    </main>
  );
}
