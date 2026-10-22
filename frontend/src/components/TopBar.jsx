export default function TopBar({ filename, nCustomers, nRows, isDemo, onReset, reportStatus, onOpenReport }) {
  return (
    <header className="topbar">
      <div className="topbar-info">
        <span className="topbar-file">{isDemo ? "Demo veri seti" : filename}</span>
        {isDemo && <span className="topbar-badge">Sentetik veri</span>}
        <span className="topbar-meta">
          {nCustomers.toLocaleString("tr-TR")} müşteri, {nRows.toLocaleString("tr-TR")} satır
        </span>
      </div>
      <div className="topbar-actions">
        {reportStatus === "ready" && (
          <button className="topbar-report is-ready" onClick={onOpenReport}>
            CRM raporunuz hazır
          </button>
        )}
        {reportStatus === "loading" && <span className="topbar-report-pending">Rapor hazırlanıyor…</span>}
        {reportStatus === "idle" && (
          <button className="btn-secondary" onClick={onOpenReport}>
            CRM raporu oluştur
          </button>
        )}
        <button className="btn-secondary" onClick={onReset}>
          {isDemo ? "Kendi verini yükle" : "Yeni dosya yükle"}
        </button>
      </div>
    </header>
  );
}
