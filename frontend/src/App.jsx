import { useEffect, useState } from "react";
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
import { deleteSession, startDemo, warmUpBackend } from "./api";

export default function App() {
  const [view, setView] = useState("landing");
  const [active, setActive] = useState("upload");
  const [dataset, setDataset] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState(null);

  useEffect(() => {
    warmUpBackend();
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [view]);

  function handleUploaded(result) {
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
      setDemoError(
        `Demo başlatılamadı: ${err.message} Sunucu uyanıyor olabilir; birkaç saniye sonra tekrar deneyin.`
      );
    } finally {
      setDemoLoading(false);
    }
  }

  function openUpload() {
    setActive("upload");
    setView("app");
  }

  function clearSession() {
    if (dataset?.session_id) {
      deleteSession(dataset.session_id).catch(() => {
        // best-effort cleanup — the in-memory session store drops it on
        // restart anyway, so a failed delete isn't worth surfacing
      });
    }
    setDataset(null);
  }

  function handleReset() {
    clearSession();
    setActive("upload");
  }

  if (view === "landing") {
    return (
      <LandingPage
        onStartDemo={handleStartDemo}
        onUpload={openUpload}
        demoLoading={demoLoading}
        demoError={demoError}
      />
    );
  }

  const sessionId = dataset?.session_id;

  return (
    <div className="app-shell">
      <Sidebar
        active={active}
        onSelect={setActive}
        hasSession={Boolean(sessionId)}
        onHome={() => setView("landing")}
      />
      <div className="content-area">
        {dataset && active !== "upload" && (
          <TopBar
            filename={dataset.filename}
            nCustomers={dataset.n_customers}
            nRows={dataset.n_rows}
            isDemo={dataset.is_demo}
            onReset={handleReset}
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
          {active === "segments" && sessionId && <SegmentsScreen sessionId={sessionId} />}
          {active === "cltv" && sessionId && <CltvScreen sessionId={sessionId} />}
          {active === "churn" && sessionId && <ChurnScreen sessionId={sessionId} />}
          {active === "recommendations" && sessionId && <RecommendationsScreen sessionId={sessionId} />}
          {active === "windows" && sessionId && <WindowSearchScreen sessionId={sessionId} />}
        </main>
      </div>
    </div>
  );
}
