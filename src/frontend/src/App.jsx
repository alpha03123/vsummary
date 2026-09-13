import { useState, useEffect, useRef } from "react";
import { useWorkspaceController } from "./features/workspace/model/useWorkspaceController";
import { WorkspacePage } from "./features/workspace/ui/WorkspacePage";
import { WorkspaceVideoScopeEmbed } from "./features/workspace/ui/WorkspaceVideoScopeEmbed";
import { buildWorkspacePageModel } from "./features/workspace/ui/workspacePageModel";
import { MotionShowcase } from "./dev/MotionShowcase";

export function App() {
  const isVideoScopeEmbed = new URLSearchParams(window.location.search).get("embed") === "video-scope";
  if (isVideoScopeEmbed) {
    return <WorkspaceVideoScopeEmbed />;
  }

  return <WorkspaceApplication />;
}

function WorkspaceApplication() {
  const controller = useWorkspaceController();
  const page = buildWorkspacePageModel(controller);
  const [isTestMode, setIsTestMode] = useState(window.location.hash === '#test');
  const deepLinkHandled = useRef(false);

  useEffect(() => {
    if (deepLinkHandled.current) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const seriesId = params.get("series");
    const videoId = params.get("video");
    if (!seriesId || !videoId) {
      deepLinkHandled.current = true;
      return;
    }
    const series = controller.state.library?.series?.find((item) => item.id === seriesId);
    if (!series) {
      return;
    }
    deepLinkHandled.current = true;
    if (series.videos.some((video) => video.id === videoId)) {
      controller.onSelectVideo(seriesId, videoId);
    }
  }, [controller.onSelectVideo, controller.state.library]);

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
