import { Route, Routes } from "react-router-dom";
import TopBar from "./components/TopBar";
import ToastHost from "./components/ToastHost";
import BusyBar from "./components/BusyBar";
import Dashboard from "./pages/Dashboard";
import ProjectShell from "./pages/ProjectShell";
import Workspace from "./pages/Workspace";
import ImportWizard from "./pages/ImportWizard";
import CodeLibrary from "./pages/CodeLibrary";
import QaPage from "./pages/QaPage";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <div className="h-full flex flex-col bg-base text-ink">
      <TopBar />
      <main className="flex-1 min-h-0 relative">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects/:projectId" element={<ProjectShell />}>
            <Route index element={<Workspace />} />
            <Route path="import" element={<ImportWizard />} />
            <Route path="codes" element={<CodeLibrary />} />
            <Route path="qa" element={<QaPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
        <BusyBar />
      </main>
      <ToastHost />
    </div>
  );
}
