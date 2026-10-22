export default function TopBar({ filename, nCustomers, nRows, isDemo, onReset }) {
  return (
    <header className="topbar">
      <div className="topbar-info">
        <span className="topbar-file">{isDemo ? "Demo veri seti" : filename}</span>
        {isDemo && <span className="topbar-badge">Sentetik veri</span>}
        <span className="topbar-meta">
          {nCustomers.toLocaleString("tr-TR")} müşteri, {nRows.toLocaleString("tr-TR")} satır
        </span>
      </div>
      <button className="btn-secondary" onClick={onReset}>
        {isDemo ? "Kendi verini yükle" : "Yeni dosya yükle"}
      </button>
    </header>
  );
}
