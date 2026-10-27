"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { requestDossier } from "@/lib/api";

const today = () => new Date().toLocaleDateString("en-CA"); // local date, YYYY-MM-DD

export default function IntakePage() {
  const router = useRouter();
  const [parcel, setParcel] = useState("");
  const [serial, setSerial] = useState("");
  const [seller, setSeller] = useState("");
  const [saleDate, setSaleDate] = useState(today());
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await requestDossier({
      parcel_input: parcel.trim(),
      title_serial: serial.trim(),
      seller_name: seller.trim(),
      sale_date: saleDate || today(),
    });
    try {
      // the sale date goes with it so the dossier page can say whether windows were open then
      sessionStorage.setItem("dossier", JSON.stringify({ ...result, saleDate: saleDate || today() }));
    } catch {
      // private window etc. The dossier page will say nothing was found.
    }
    router.push("/dossier");
  }

  return (
    <main className="container">
      <h1>Land title check</h1>
      <p className="lead">
        Before you pay for an official search or an advocate, check the plot against
        public records: Gazette notices, land court judgments and cancelled title serials.
      </p>

      <form onSubmit={onSubmit} className="card">
        <label>
          Parcel number <span className="req">*</span>
          <input required value={parcel} onChange={(e) => setParcel(e.target.value)}
                 placeholder="e.g. NAIROBI/BLOCK 9/123 or LR 12715/288" />
        </label>
        <label>
          Title deed serial number
          <input value={serial} onChange={(e) => setSerial(e.target.value)}
                 inputMode="numeric" placeholder="e.g. 5253012" />
        </label>
        <label>
          Seller&apos;s name
          <input value={seller} onChange={(e) => setSeller(e.target.value)} />
        </label>
        <label>
          Planned sale date
          <input type="date" value={saleDate} onChange={(e) => setSaleDate(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || !parcel.trim()}>
          {busy ? "Checking records…" : "Check this plot"}
        </button>
      </form>

      <p className="fine">
        This tool can flag warning signs. It can&apos;t confirm a title is genuine: forged
        titles and impersonated owners leave no public trace. Always do an official search
        and use an advocate.
      </p>
      <p className="fine"><a href="/providers">AI provider settings</a></p>
    </main>
  );
}
