import { useState } from "react";
import { downloadCsv } from "../csv";

const BADGE_COLUMNS = new Set(["segment", "risk_segment"]);

function badgeClass(value) {
  const v = String(value).toLowerCase();
  if (v.includes("düşük")) return "risk-dusuk";
  if (v.includes("orta")) return "risk-orta";
  if (v.includes("çok")) return "risk-cok";
  if (v.includes("yüksek") || v === "very high" || v === "high") return "risk-yuksek";
  if (v === "low" || v === "mid") return "risk-dusuk";
  return "risk-orta";
}

function formatCell(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString("tr-TR") : value.toFixed(2);
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
                      <span className={`badge ${badgeClass(row[col.key])}`}>{row[col.key]}</span>
                    ) : (
                      formatCell(row[col.key])
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
