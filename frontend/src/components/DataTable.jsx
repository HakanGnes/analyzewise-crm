import { useState } from "react";
import { downloadCsv } from "../csv";

const BADGE_COLUMNS = new Set(["segment", "risk_segment", "quadrant"]);

// Status colors (green → red) are reserved for columns whose values *mean*
// good/bad: churn risk bands, and the one risk × value quadrant that needs
// action. Segment names and value tiers are identities, not states, so they
// get a neutral badge — "very high" CLTV must never render in red.
function badgeClass(column, value) {
  const v = String(value).toLowerCase();
  if (column === "risk_segment") {
    if (v.startsWith("düşük")) return "risk-dusuk";
    if (v.startsWith("orta")) return "risk-orta";
    if (v.startsWith("çok")) return "risk-cok";
    return "risk-yuksek";
  }
  if (column === "quadrant" && v === "değerli, riskte") return "risk-cok";
  return "badge-neutral";
}

// Identifier columns are labels, not quantities — "12346" must not render as "12.346"
const ID_COLUMNS = new Set(["CustomerNo", "TransactionNo", "ProductNo", "product_id"]);

// Amounts keep two decimals so a column never mixes "781" and "1.239,93"
const MONEY_COLUMNS = new Set(["monetary", "historical_spend", "predicted_cltv"]);

// 0–1 probabilities read better as percentages, and 1.0 must not collapse to "1"
const PROBABILITY_COLUMNS = new Set(["churn_probability"]);

function formatCell(value, key) {
  if (value === null || value === undefined) return "—";
  if (ID_COLUMNS.has(key)) return String(value);
  if (PROBABILITY_COLUMNS.has(key) && typeof value === "number") return `%${Math.round(value * 100)}`;
  if (typeof value === "number") {
    if (MONEY_COLUMNS.has(key)) return value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return Number.isInteger(value)
      ? value.toLocaleString("tr-TR")
      : value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(value);
}

export default function DataTable({ columns, rows, pageSize = 15, exportFilename }) {
  const [page, setPage] = useState(0);

  if (!rows || rows.length === 0) {
    return <div className="empty-state">Gösterilecek satır yok.</div>;
  }

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const clampedPage = Math.min(page, pageCount - 1);
  const start = clampedPage * pageSize;
  const visibleRows = rows.slice(start, start + pageSize);

  return (
    <div>
      <div className="table-toolbar">
        <span className="receipt-note" style={{ margin: 0 }}>
          {rows.length.toLocaleString("tr-TR")} satır
        </span>
        {exportFilename && (
          <button className="link-btn" onClick={() => downloadCsv(exportFilename, columns, rows)}>
            CSV indir
          </button>
        )}
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, i) => (
              <tr key={start + i}>
                {columns.map((col) => (
                  <td key={col.key}>
                    {BADGE_COLUMNS.has(col.key) ? (
                      <span className={`badge ${badgeClass(col.key, row[col.key])}`}>{row[col.key]}</span>
                    ) : (
                      formatCell(row[col.key], col.key)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div className="pagination">
          <button className="page-btn" disabled={clampedPage === 0} onClick={() => setPage(clampedPage - 1)}>
            ← Önceki
          </button>
          <span className="page-indicator">
            Sayfa {clampedPage + 1} / {pageCount}
          </span>
          <button
            className="page-btn"
            disabled={clampedPage >= pageCount - 1}
            onClick={() => setPage(clampedPage + 1)}
          >
            Sonraki →
          </button>
        </div>
      )}
    </div>
  );
}
