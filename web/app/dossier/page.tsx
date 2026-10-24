"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Claim, Dossier, Verdict } from "@/lib/contracts";

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
      <blockquote>“{c.quote}”</blockquote>
      <small>Source: {c.source_id}</small>
      {c.reject_reason && <small className="reject"> · Not counted: {c.reject_reason}</small>}
    </li>
  );
}

export default function DossierPage() {
  const [data, setData] = useState<{ dossier: Dossier; fromMock: boolean } | null>(null);
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

  const { dossier: d, fromMock } = data;
  const v = VERDICT_INFO[d.verdict];

  return (
    <main className="container">
      <Link href="/">← Check another plot</Link>

      {fromMock && (
        <p className="mock-banner">
          Demo data: the agent backend isn&apos;t connected yet, so this is a mock result.
        </p>
      )}

      <h1>{d.parcel_input}</h1>

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
          <ul>
            {d.objection_windows.map((w) => (
              <li key={w.notice_id}>
                Notice {w.notice_id}: {w.open ? "open until" : "closed on"} {w.closes_on}
              </li>
            ))}
          </ul>
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
          <ul>{d.advocate_review.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      )}

      <section>
        <h2>Checks you still need to do</h2>
        <ol>{d.remaining_checks.map((c) => <li key={c}>{c}</li>)}</ol>
      </section>

      <p className="fine">Run ID: {d.run_id}</p>
    </main>
  );
}
