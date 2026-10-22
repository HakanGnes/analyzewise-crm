const NAV_ITEMS = [
  { id: "overview", label: "Genel Bakış", icon: "📊" },
  { id: "segments", label: "Segmentasyon", icon: "👥" },
  { id: "cltv", label: "CLTV Tahmini", icon: "💰" },
  { id: "churn", label: "Churn Tahmini", icon: "⚠️" },
  { id: "recommendations", label: "Ürün Önerisi", icon: "🎯" },
  { id: "windows", label: "Pencere Araması", icon: "🔍" },
];

export default function Sidebar({ active, onSelect, hasSession, onHome }) {
  return (
    <aside className="sidebar">
      <button className="sidebar-brand" onClick={onHome} title="Tanıtım sayfasına dön">
        <div className="sidebar-brand-mark">
          Analyze<span>Wise</span>
        </div>
        <div className="sidebar-brand-sub">CRM Analytics</div>
      </button>
      <nav className="sidebar-nav">
        <button
          className={`sidebar-nav-item${active === "upload" ? " active" : ""}`}
          onClick={() => onSelect("upload")}
        >
          <span className="sidebar-nav-icon">⬆️</span>
          Veri Yükle
        </button>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav-item${active === item.id ? " active" : ""}`}
            onClick={() => onSelect(item.id)}
            disabled={!hasSession}
          >
            <span className="sidebar-nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">v0.3 · Faz 3</div>
    </aside>
  );
}
