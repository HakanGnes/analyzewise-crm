import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import LandingPage from "./screens/LandingPage";
import UploadScreen from "./screens/UploadScreen";
import OverviewScreen from "./screens/OverviewScreen";
import SegmentsScreen from "./screens/SegmentsScreen";
import CltvScreen from "./screens/CltvScreen";
import ChurnScreen from "./screens/ChurnScreen";
import RecommendationsScreen from "./screens/RecommendationsScreen";
import WindowSearchScreen from "./screens/WindowSearchScreen";
import ReportScreen from "./screens/ReportScreen";
import { deleteSession, getReportHtml, startDemo, warmUpBackend } from "./api";

const DEFAULT_SETTINGS = { k: 6, auto: false, approach: "single" };
const EMPTY_REPORT = { html: null, loading: false, error: null, key: null };
// Once the person has looked at both model screens, every model the report
// needs is trained and cached — generating it then is cheap, so do it
// automatically in the background.
const AUTO_REPORT_AFTER = ["cltv", "churn"];

const settingsKey = (s) => `${s.auto ? "auto" : s.k}:${s.approach}`;

export default function App() {
  const [view, setView] = useState("landing");
  const [active, setActive] = useState("upload");
  const [dataset, setDataset] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState(null);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [visited, setVisited] = useState(() => new Set());
  const [report, setReport] = useState(EMPTY_REPORT);
  const reportRequest = useRef(0);

  const sessionId = dataset?.session_id;

  useEffect(() => {
    warmUpBackend();
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [view, active]);

  useEffect(() => {
    setVisited((prev) => (prev.has(active) ? prev : new Set(prev).add(active)));
  }, [active]);

  const generateReport = useCallback(() => {
    if (!sessionId) return;
    const requestId = ++reportRequest.current;
    const key = settingsKey(settings);
    setReport({ html: null, loading: true, error: null, key });
    getReportHtml(sessionId, settings)
      .then((html) => requestId === reportRequest.current && setReport({ html, loading: false, error: null, key }))
      .catch(
        (err) =>
          requestId === reportRequest.current &&
          setReport({ html: null, loading: false, error: err.message, key })
      );
  }, [sessionId, settings]);

  // A report built for other settings is stale: drop it.
  useEffect(() => {
    setReport((r) => (r.key && r.key !== settingsKey(settings) ? EMPTY_REPORT : r));
  }, [settings]);

  // Automatic report once the person has seen the model screens.
  useEffect(() => {
    if (!sessionId || report.html || report.loading || report.error) return;
    if (AUTO_REPORT_AFTER.every((s) => visited.has(s))) generateReport();
  }, [sessionId, visited, report, generateReport]);

  function resetSessionState() {
    setSettings(DEFAULT_SETTINGS);
    setVisited(new Set());
    reportRequest.current += 1;
    setReport(EMPTY_REPORT);
  }

  function handleUploaded(result) {
    resetSessionState();
    setDataset(result);
    setActive("overview");
    setView("app");
  }

  async function handleStartDemo() {
    setDemoLoading(true);
    setDemoError(null);
    try {
      handleUploaded(await startDemo());
    } catch (err) {
      setDemoError(`Demo başlatılamadı: ${err.message} Sunucu uyanıyor olabilir; birkaç saniye sonra tekrar deneyin.`);
    } finally {
      setDemoLoading(false);
    }
  }

  function openUpload() {
    setActive("upload");
    setView("app");
  }

  function handleReset() {
    if (dataset?.session_id) {
      deleteSession(dataset.session_id).catch(() => {
        // best-effort cleanup — the in-memory session store drops it on
        // restart anyway, so a failed delete isn't worth surfacing
      });
    }
    setDataset(null);
    resetSessionState();
    setActive("upload");
  }

  if (view === "landing") {
    return (
      <LandingPage onStartDemo={handleStartDemo} onUpload={openUpload} demoLoading={demoLoading} demoError={demoError} />
    );
  }

  const reportStatus = report.html ? "ready" : report.loading ? "loading" : "idle";

  return (
    <div className="app-shell">
      <Sidebar
        active={active}
        onSelect={setActive}
        hasSession={Boolean(sessionId)}
        onHome={() => setView("landing")}
        reportStatus={reportStatus}
      />
      <div className="content-area">
        {dataset && active !== "upload" && (
          <TopBar
            filename={dataset.filename}
            nCustomers={dataset.n_customers}
            nRows={dataset.n_rows}
            isDemo={dataset.is_demo}
            onReset={handleReset}
            reportStatus={active === "report" ? null : reportStatus}
            onOpenReport={() => setActive("report")}
          />
        )}
        <main className="main">
          {active === "upload" && (
            <UploadScreen
              dataset={dataset}
              onUploaded={handleUploaded}
              onStartDemo={handleStartDemo}
              demoLoading={demoLoading}
              demoError={demoError}
            />
          )}
          {active === "overview" && sessionId && <OverviewScreen sessionId={sessionId} />}
          {active === "segments" && sessionId && (
            <SegmentsScreen
              sessionId={sessionId}
              settings={settings}
              onSettingsChange={(s) => setSettings((cur) => ({ ...cur, k: s.k, auto: s.auto }))}
            />
          )}
          {active === "cltv" && sessionId && (
            <CltvScreen
              sessionId={sessionId}
              approach={settings.approach}
              onApproachChange={(approach) => setSettings((cur) => ({ ...cur, approach }))}
            />
          )}
          {active === "churn" && sessionId && <ChurnScreen sessionId={sessionId} approach={settings.approach} />}
          {active === "recommendations" && sessionId && <RecommendationsScreen sessionId={sessionId} />}
          {active === "windows" && sessionId && <WindowSearchScreen sessionId={sessionId} />}
          {active === "report" && sessionId && (
            <ReportScreen sessionId={sessionId} settings={settings} report={report} onGenerate={generateReport} />
          )}
        </main>
      </div>
    </div>
  );
}
