export default function TopBar({ filename, nCustomers, nRows, onReset }) {
  return (
    <header className="topbar">
      <div className="topbar-info">
        <span className="topbar-file">{filename}</span>
        <span className="topbar-meta">
          {nCustomers.toLocaleString("tr-TR")} müşteri · {nRows.toLocaleString("tr-TR")} satır
        </span>
      </div>
      <button className="btn-secondary" onClick={onReset}>
        Yeni Dosya Yükle
      </button>
    </header>
  );
}
