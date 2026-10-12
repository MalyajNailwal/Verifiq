import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const DOC_TYPES = [
  ["title_deed", "Title deed"],
  ["valuation_report", "Valuation report"],
  ["legal_opinion", "Legal opinion"],
  ["spv_papers", "SPV papers"],
  ["other", "Other"],
];

export default function NewCasePage() {
  const nav = useNavigate();
  const [assetName, setAssetName] = useState("");
  const [assetType, setAssetType] = useState("real_estate");
  const [jurisdiction, setJurisdiction] = useState("");
  const [rows, setRows] = useState([]); // {file, docType}
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [caseId, setCaseId] = useState(null);
  const [stage, setStage] = useState("form");

  function addFiles(files) {
    setRows((r) => [...r, ...Array.from(files).map((file) => ({ file, docType: "title_deed" }))]);
  }

  function setRowType(i, docType) {
    setRows((r) => r.map((row, j) => (i === j ? { ...row, docType } : row)));
  }

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await api.createCase({
        asset_name: assetName,
        asset_type: assetType,
        jurisdiction: jurisdiction || null,
      });
      const cid = created.id;
      setCaseId(cid);
      if (rows.length) {
        await api.uploadDocuments(cid, rows.map((r) => r.file), rows.map((r) => r.docType));
      }
      setStage("done");
      api.runCase(cid).catch(() => {});
      nav(`/cases/${cid}`);
    } catch (err) {
      setError(String(err.message || err));
      setStage("form");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="relative">
      <h1 className="font-display font-black text-4xl">Open a verification case</h1>
      <p className="mt-2 text-ink/60 max-w-2xl">
        Upload the document pack — title deed, valuation, legal opinion, SPV papers.
        Verifiq extracts key facts, cross-checks them, and routes anything doubtful to
        human review.
      </p>

      <form onSubmit={submit} className="mt-8 grid gap-6 max-w-3xl">
        <fieldset className="border-2 border-ink p-5 bg-white/60">
          <legend className="font-mono text-xs uppercase tracking-widest px-2">1 · Asset</legend>
          <div className="grid gap-4">
            <label className="grid gap-1">
              <span className="font-mono text-xs uppercase">Asset name</span>
              <input
                required value={assetName} onChange={(e) => setAssetName(e.target.value)}
                placeholder="Plot 42, Riverside Estate"
                className="border border-rule px-3 py-2 bg-paper focus:outline-none focus:border-ink"
              />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="grid gap-1">
                <span className="font-mono text-xs uppercase">Asset type</span>
                <select
                  value={assetType} onChange={(e) => setAssetType(e.target.value)}
                  className="border border-rule px-3 py-2 bg-paper"
                >
                  <option value="real_estate">real_estate</option>
                  <option value="land">land</option>
                </select>
              </label>
              <label className="grid gap-1">
                <span className="font-mono text-xs uppercase">Jurisdiction (optional)</span>
                <input
                  value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}
                  placeholder="IN-KA"
                  className="border border-rule px-3 py-2 bg-paper"
                />
              </label>
            </div>
          </div>
        </fieldset>

        <fieldset className="border-2 border-ink p-5 bg-white/60">
          <legend className="font-mono text-xs uppercase tracking-widest px-2">2 · Documents</legend>
          <label className="grid gap-1">
            <span className="font-mono text-xs uppercase">Attach files</span>
            <input
              type="file" multiple accept=".txt,.md,.pdf"
              onChange={(e) => addFiles(e.target.files)}
              className="border border-dashed border-ink/40 px-3 py-6 bg-paper text-center cursor-pointer"
            />
          </label>
          {rows.length > 0 && (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="font-mono text-xs uppercase text-left border-b border-rule">
                  <th className="py-2">File</th>
                  <th className="py-2 w-56">Document type</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-rule/60">
                    <td className="py-2 font-mono text-xs">{row.file.name}</td>
                    <td className="py-2">
                      <select
                        value={row.docType}
                        onChange={(e) => setRowType(i, e.target.value)}
                        className="border border-rule px-2 py-1 bg-paper w-full"
                      >
                        {DOC_TYPES.map(([v, label]) => (
                          <option key={v} value={v}>{label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setRows((r) => r.filter((_, j) => j !== i))}
                        className="font-mono text-xs text-stamp hover:underline"
                      >
                        remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </fieldset>

        {error && (
          <p className="border-2 border-stamp text-stamp font-mono text-sm px-4 py-3">{error}</p>
        )}

        <button
          type="submit" disabled={busy}
          className="justify-self-start bg-ink text-paper px-8 py-3 font-mono uppercase tracking-widest text-sm hover:bg-ink/85 disabled:opacity-50"
        >
          {busy ? "Opening case…" : "Create case & run pipeline"}
        </button>
      </form>
    </section>
  );
}
