import { useMemo, useState } from "react";
import { reinspectUpload, confirmUpload } from "../api";

const NONE = "";

const STATUS = {
  found: { text: "Bulundu", cls: "map-status-found" },
  check: { text: "Kontrol et", cls: "map-status-check" },
  mine: { text: "Senin seçimin", cls: "map-status-mine" },
  missing: { text: "Seçilmedi", cls: "map-status-missing" },
  empty: { text: "Yok", cls: "map-status-empty" },
};

function problemsOf(mapping) {
  const out = [];
  if (!mapping.customer_id) out.push("Müşteriyi gösteren kolonu seçin.");
  if (!mapping.date) out.push("Tarih kolonunu seçin.");
  if (!mapping.price && !mapping.amount) out.push("Birim fiyat ya da satır tutarından birini seçin.");
  const used = Object.values(mapping).filter(Boolean);
  const dupes = [...new Set(used.filter((c, i) => used.indexOf(c) !== i))];
  if (dupes.length) out.push(`Aynı kolon birden fazla yerde seçili: ${dupes.join(", ")}.`);
  return out;
}

function initialMapping(inspection) {
  return Object.fromEntries(inspection.roles.map((r) => [r.role, r.column ?? NONE]));
}

export default function MappingStep({ inspection: initial, onDone, onCancel }) {
  const [inspection, setInspection] = useState(initial);
  const [mapping, setMapping] = useState(() => initialMapping(initial));
  const [dateOrder, setDateOrder] = useState("auto");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const columns = useMemo(() => Object.fromEntries(inspection.columns.map((c) => [c.name, c])), [inspection]);
  const suggested = useMemo(() => initialMapping(inspection), [inspection]);
  const problems = problemsOf(mapping);
  const dateAmbiguous = mapping.date && columns[mapping.date]?.date_ambiguous;

  function statusOf(role) {
    const value = mapping[role.role];
    if (!value) return role.required || (["price", "amount"].includes(role.role) && !mapping.price && !mapping.amount) ? STATUS.missing : STATUS.empty;
    if (value !== suggested[role.role]) return STATUS.mine;
    return role.confidence === "yüksek" ? STATUS.found : STATUS.check;
  }

  async function changeSheet(sheet) {
    setBusy("sheet");
    setError(null);
    try {
      const next = await reinspectUpload(inspection.upload_id, { sheet });
      setInspection(next);
      setMapping(initialMapping(next));
      setDateOrder("auto");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function confirm() {
    setBusy("confirm");
    setError(null);
    try {
      const body = { mapping: Object.fromEntries(Object.entries(mapping).map(([k, v]) => [k, v || null])), sheet: inspection.sheet, date_order: dateOrder };
      onDone(await confirmUpload(inspection.upload_id, body));
    } catch (err) {
      setError(err.message);
      setBusy(null);
    }
  }

  const foundCount = inspection.roles.filter((r) => r.column).length;

  return (
    <section className="mapping" aria-labelledby="mapping-title">
      <div className="mapping-head">
        <div>
          <h2 className="mapping-title" id="mapping-title">
            Verini böyle anladık
          </h2>
          <p className="mapping-sub">
            <strong>{inspection.filename}</strong> · {inspection.n_rows.toLocaleString("tr-TR")} satır
            {inspection.header_row > 1 && ` · başlıklar ${inspection.header_row}. satırda bulundu`}
            {` · ${foundCount} kolon otomatik eşleşti`}. Yanlış olanı listeden düzeltin, sonra analize başlayın.
          </p>
        </div>
        {inspection.sheets.length > 1 && (
          <label className="control-group">
            <span className="control-label">Sayfa</span>
            <select className="select" value={inspection.sheet} disabled={!!busy} onChange={(e) => changeSheet(e.target.value)}>
              {inspection.sheets.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="data-table-wrap">
        <table className="data-table mapping-table">
          <thead>
            <tr>
              <th scope="col">Sistemin ihtiyacı</th>
              <th scope="col">Dosyandaki kolon</th>
              <th scope="col">Örnek değerler</th>
              <th scope="col">Durum</th>
            </tr>
          </thead>
          <tbody>
            {inspection.roles.map((role) => {
              const status = statusOf(role);
              const col = mapping[role.role] ? columns[mapping[role.role]] : null;
              return (
                <tr key={role.role}>
                  <td className="map-role">
                    <span className="map-role-label">
                      {role.label}
                      {role.required && <span className="map-required"> *</span>}
                    </span>
                    <span className="map-help">{role.help}</span>
                  </td>
                  <td className="map-select">
                    <select
                      className="select"
                      aria-label={`${role.label} kolonu`}
                      value={mapping[role.role]}
                      onChange={(e) => setMapping((m) => ({ ...m, [role.role]: e.target.value }))}
                    >
                      <option value={NONE}>— yok —</option>
                      {inspection.columns.map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="map-samples">
                    {col ? col.samples.slice(0, 3).map((v, i) => <code key={i}>{v}</code>) : <span className="map-none">—</span>}
                  </td>
                  <td>
                    <span className={`map-status ${status.cls}`} title={mapping[role.role] === suggested[role.role] ? role.reason : undefined}>
                      {status.text}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {dateAmbiguous && (
        <div className="map-date-order" role="group" aria-label="Tarih sırası">
          <span>
            <strong>Tarih sırası belirsiz:</strong> {columns[mapping.date].samples[0]} gibi değerler hem gün/ay hem ay/gün
            olarak okunabiliyor.
          </span>
          <div className="radio-group">
            <button className={`radio-pill${dateOrder !== "monthfirst" ? " active" : ""}`} onClick={() => setDateOrder("dayfirst")}>
              Gün/Ay (22/10)
            </button>
            <button className={`radio-pill${dateOrder === "monthfirst" ? " active" : ""}`} onClick={() => setDateOrder("monthfirst")}>
              Ay/Gün (10/22)
            </button>
          </div>
        </div>
      )}

      {(inspection.hints.length > 0 || problems.length > 0) && (
        <ul className="map-problems">
          {inspection.hints.map((h) => (
            <li key={h}>{h}</li>
          ))}
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {error && <p className="error-state">{error}</p>}

      <div className="map-actions">
        <button className="btn-primary" onClick={confirm} disabled={problems.length > 0 || !!busy}>
          {busy === "confirm" ? "Veri hazırlanıyor…" : "Doğru, analize başla"}
        </button>
        <button className="btn-secondary" onClick={onCancel} disabled={!!busy}>
          Başka dosya seç
        </button>
      </div>

      <details className="map-preview">
        <summary>Dosyanın ilk satırları</summary>
        <div className="data-table-wrap map-preview-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {inspection.preview.columns.map((c) => (
                  <th key={c} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {inspection.preview.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((v, j) => (
                    <td key={j}>{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
