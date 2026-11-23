import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import AppLayout from "./layouts/AppLayout";
import { JobProvider } from "./hooks/useJob";
import { ToastProvider } from "./hooks/useToast";
import Overview from "./pages/Overview";
import LogExplorer from "./pages/LogExplorer";
import Clusters from "./pages/Clusters";
import ClusterDetail from "./pages/ClusterDetail";
import Anomalies from "./pages/Anomalies";
import Insights from "./pages/Insights";
import Evaluation from "./pages/Evaluation";
import UploadPage from "./pages/Upload";
import Reports from "./pages/Reports";
import { Empty } from "./components/ui";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ToastProvider>
      <JobProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Overview />} />
              <Route path="logs" element={<LogExplorer />} />
              <Route path="clusters" element={<Clusters />} />
              <Route path="clusters/:id" element={<ClusterDetail />} />
              <Route path="anomalies" element={<Anomalies />} />
              <Route path="insights" element={<Insights />} />
              <Route path="evaluation" element={<Evaluation />} />
              <Route path="upload" element={<UploadPage />} />
              <Route path="reports" element={<Reports />} />
              <Route path="*" element={<Empty title="Page not found" />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </JobProvider>
    </ToastProvider>
  </React.StrictMode>
);
