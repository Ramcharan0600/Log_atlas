import { Boxes, FileDown, FlaskConical, LayoutDashboard, Lightbulb, ScrollText, Siren, Upload } from "lucide-react";

export const NAV = [
  ["/", "Overview", LayoutDashboard], ["/logs", "Log Explorer", ScrollText], ["/clusters", "Cluster Explorer", Boxes], ["/anomalies", "Anomaly Center", Siren],
  ["/insights", "Root-Cause Insights", Lightbulb], ["/evaluation", "Model Evaluation", FlaskConical], ["/upload", "Upload & Analysis", Upload], ["/reports", "Reports", FileDown],
] as const;
