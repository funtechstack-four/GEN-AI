"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Model = { id: string; disposition: string };
type Provider = {
  id: string; name: string; base_url: string;
  status: "online" | "unauthorized" | "offline";
  models: Model[]; token_configured: boolean; needs_token: boolean; selected_model: string;
};

async function readProvider(response: Response): Promise<Provider> {
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data as Provider;
}

export default function ProvidersPage() {
  const [provider, setProvider] = useState<Provider | null>(null);
  const [url, setUrl] = useState("http://127.0.0.1:8088/v1");
  const [token, setToken] = useState("");
  const [model, setModel] = useState("meterless/auto");
  const [message, setMessage] = useState("Reply with the word ready.");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const next = await readProvider(await fetch(`${API_URL}/providers/meterless`));
    setProvider(next);
    setUrl(next.base_url);
    setModel(next.selected_model || (next.models[0]?.id ?? "meterless/auto"));
  }, []);

  useEffect(() => { refresh().catch((e) => setError(e.message)); }, [refresh]);

  async function save() {
    setBusy(true); setError(""); setReply("");
    try {
      const next = await readProvider(await fetch(`${API_URL}/providers/meterless`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ base_url: url, token: token || null, model }),
      }));
      setProvider(next); setUrl(next.base_url); setToken("");
      setModel(next.selected_model || next.models[0]?.id || "meterless/auto");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save provider"); }
    finally { setBusy(false); }
  }

  async function detect() {
    setBusy(true); setError(""); setReply("");
    try {
      const next = await readProvider(await fetch(`${API_URL}/providers/meterless/detect`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: token || null }),
      }));
      setProvider(next);
      if (next.base_url) setUrl(next.base_url);
      setModel(next.selected_model || next.models[0]?.id || "meterless/auto");
      if (next.status === "online") setToken("");
      if (next.status === "offline") setError("No Meterless Runtime with a compatible model was found. Check the token and runtime ports.");
    } catch (e) { setError(e instanceof Error ? e.message : "Auto Detect failed"); }
    finally { setBusy(false); }
  }

  async function chooseModel(nextModel: string) {
    setModel(nextModel);
    if (!provider) return;
    setError("");
    try {
      const next = await readProvider(await fetch(`${API_URL}/providers/meterless`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ base_url: provider.base_url || url, model: nextModel }),
      }));
      setProvider(next);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save routing mode"); }
  }

  async function send() {
    setBusy(true); setError(""); setReply("");
    try {
      const response = await fetch(`${API_URL}/providers/meterless/chat`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ model, message }), signal: AbortSignal.timeout(180_000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
      if (typeof data.content !== "string") throw new Error("Runtime returned a non-text response");
      setReply(data.content);
    } catch (e) { setError(e instanceof Error ? e.message : "Chat request failed"); }
    finally { setBusy(false); }
  }

  const status = provider?.status ?? "offline";
  return (
    <main className="container">
      <p><a href="/">← Land title check</a></p>
      <h1>AI providers</h1>
      <p className="lead">Configure Meterless Runtime as an OpenAI-compatible provider. Credentials are stored by the local API, not in browser storage.</p>

      <section className="card">
        <h2>{provider?.name ?? "Meterless Runtime"}</h2>
        <p className={`provider-status provider-${status}`} role="status">
          {status === "online" ? "Online" : status === "unauthorized" ? "Unauthorized — paste the Runtime token" : "Offline"}
        </p>
        <label>
          Runtime URL or connect link
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8088/v1 or a /connect#k=… link" />
        </label>
        <label>
          Runtime token {provider?.token_configured ? <span className="fine-tight">Token saved</span> : null}
          <input type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste token (rt-local is not accepted)" />
        </label>
        {status === "unauthorized" ? <p className="mock-banner">The runtime is responding, but rejected the saved token. Paste a valid token and save.</p> : null}
        <div className="provider-actions">
          <button type="button" onClick={save} disabled={busy}>Save and check</button>
          <button type="button" className="secondary" onClick={detect} disabled={busy}>Auto Detect</button>
        </div>
        {provider?.models.length ? <label>
          Routing mode
          <select value={model} onChange={(e) => chooseModel(e.target.value)}>
            {provider.models.map((item) => <option key={item.id} value={item.id}>{item.id}{item.disposition === "other" ? " (unrecognized; preserved)" : ""}</option>)}
          </select>
        </label> : null}
      </section>

      <section className="card provider-chat">
        <h2>Plain-text request check</h2>
        <p className="fine-tight">Sends your message as a string in the OpenAI messages format. Model startup may take a few minutes.</p>
        <label>Message<textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
        <button type="button" onClick={send} disabled={busy || status !== "online" || !provider?.models.length}>Send request</button>
        {reply ? <pre className="provider-reply">{reply}</pre> : null}
      </section>
      {error ? <p className="mock-banner" role="alert">{error}</p> : null}
    </main>
  );
}
