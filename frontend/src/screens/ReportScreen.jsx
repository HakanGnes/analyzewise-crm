import { useEffect, useRef } from "react";
import { reportXlsxUrl } from "../api";

function downloadHtml(html) {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "crm_raporu.html";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function ReportScreen({ sessionId, settings, report, onGenerate }) {
  const frameRef = useRef(null);
  const settingsLabel = `${settings.auto ? "otomatik segment sayısı" : `${settings.k} segment`}, ${
    settings.approach === "hurdle" ? "iki aşamalı" : "tek aşamalı"
  } CLTV`;

  // Generate on arrival if nothing is ready (or ready for other settings).
  useEffect(() => {
    if (!report.html && !report.loading && !report.error) onGenerate();
  }, [report.html, report.loading, report.error, onGenerate]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">CRM Raporu</h1>
        <p className="screen-subtitle">
          Ekranlarda gördüğünüz analizler tek bir raporda: yönetici özeti, segmentler ve önerilen aksiyonlar, müşteri
          değeri, churn riski, öncelikli geri kazanım listesi, ürün önerileri ve model kalitesi. Rapor, ekranlarda
          seçtiğiniz ayarlarla ({settingsLabel}) oluşturulur.
        </p>
      </div>

      <div className="report-toolbar">
        <button
          className="btn-primary"
          disabled={!report.html}
          onClick={() => frameRef.current?.contentWindow?.print()}
        >
          PDF olarak kaydet
        </button>
        <button className="btn-secondary" disabled={!report.html} onClick={() => downloadHtml(report.html)}>
          HTML olarak indir
        </button>
        <a className={`btn-secondary${report.html ? "" : " is-disabled"}`} href={report.html ? reportXlsxUrl(sessionId, settings) : undefined}>
          Excel listelerini indir
        </a>
        <button className="link-btn" onClick={onGenerate} disabled={report.loading}>
          Yeniden oluştur
        </button>
      </div>

      {report.loading && (
        <div className="loading-state">
          Rapor hazırlanıyor. Modeller bu oturumda daha önce çalışmadıysa bir dakika kadar sürebilir.
        </div>
      )}
      {report.error && (
        <div className="error-state">
          {report.error} <button className="link-btn" onClick={onGenerate}>Tekrar dene</button>
        </div>
      )}
      {report.html && !report.loading && (
        <iframe ref={frameRef} className="report-frame" title="CRM raporu önizlemesi" srcDoc={report.html} />
      )}
    </div>
  );
}
