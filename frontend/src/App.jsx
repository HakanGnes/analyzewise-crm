import { useState } from "react";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import UploadScreen from "./screens/UploadScreen";
import OverviewScreen from "./screens/OverviewScreen";
import SegmentsScreen from "./screens/SegmentsScreen";
import CltvScreen from "./screens/CltvScreen";
import ChurnScreen from "./screens/ChurnScreen";
import RecommendationsScreen from "./screens/RecommendationsScreen";
import WindowSearchScreen from "./screens/WindowSearchScreen";
import { deleteSession } from "./api";

export default function App() {
  const [active, setActive] = useState("upload");
  const [dataset, setDataset] = useState(null);

  function handleUploaded(result) {
    setDataset(result);
    setActive("overview");
  }

  function handleReset() {
    if (dataset?.session_id) {
      deleteSession(dataset.session_id).catch(() => {
        // best-effort cleanup — the in-memory session store will drop it
        // on its own if the process restarts, so a failed delete here
        // isn't worth surfacing to the person
      });
    }
    setDataset(null);
    setActive("upload");
  }

  const sessionId = dataset?.session_id;

  return (
    <div className="app-shell">
      <Sidebar active={active} onSelect={setActive} hasSession={Boolean(sessionId)} />
      <div className="content-area">
        {dataset && active !== "upload" && (
          <TopBar
            filename={dataset.filename}
            nCustomers={dataset.n_customers}
            nRows={dataset.n_rows}
            onReset={handleReset}
          />
        )}
        <main className="main">
          {active === "upload" && <UploadScreen dataset={dataset} onUploaded={handleUploaded} />}
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
