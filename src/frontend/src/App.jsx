import { useState, useEffect } from "react";
import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";
import { buildWorkspacePageModel } from "./features/workspace/ui/workspacePageModel";
import { MotionShowcase } from "./dev/MotionShowcase";

export function App() {
  const controller = useWorkspaceController();
  const page = buildWorkspacePageModel(controller);
  const [isTestMode, setIsTestMode] = useState(window.location.hash === '#test');

  useEffect(() => {
    const onHashChange = () => {
      setIsTestMode(window.location.hash === '#test');
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  if (isTestMode) {
    return <MotionShowcase />;
  }

  return (
    <WorkspacePage page={page} />
  );
}
