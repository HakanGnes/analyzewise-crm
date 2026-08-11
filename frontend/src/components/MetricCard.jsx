export default function MetricCard({ label, value, tone, note }) {
  return (
    <div className="receipt-card">
      <p className="receipt-label">{label}</p>
      <p className={`receipt-value${tone ? ` ${tone}` : ""}`}>{value}</p>
      {note && <p className="receipt-note">{note}</p>}
    </div>
  );
}
