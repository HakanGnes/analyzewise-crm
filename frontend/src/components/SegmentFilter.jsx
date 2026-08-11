export const ALL_VALUE = "__all__";

export default function SegmentFilter({ label, options, value, onChange, counts }) {
  return (
    <div className="control-group">
      <span className="control-label">{label}</span>
      <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={ALL_VALUE}>Tümü ({options.reduce((sum, o) => sum + (counts?.[o] ?? 0), 0)})</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
            {counts?.[opt] !== undefined ? ` (${counts[opt]})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
