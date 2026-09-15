import { useEffect, useRef, useState } from "react";

import { useWorkspaceController } from "../model/useWorkspaceController";
import { buildWorkspacePageModel } from "./workspacePageModel";
import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { WorkspaceVideoScopePane } from "./WorkspaceVideoScopePane";
import { ChatDrawer } from "./ChatDrawer";
import { WorkspaceGenerationOverlay } from "./WorkspaceGenerationOverlay";

const BILIBILI_INBOX_SERIES_ID = "bilibili";

function parseBilibiliTarget(sourceUrl, tabId = null) {
  if (!sourceUrl) {
    return null;
  }
  try {
    const parsed = new URL(sourceUrl);
    const match = parsed.pathname.match(/\/video\/(BV[\w]+)/i);
    if (!match) {
      return { sourceUrl, bvid: null, page: null };
    }
    const parsedPage = Number.parseInt(parsed.searchParams.get("p") ?? "1", 10);
    return {
      sourceUrl,
      bvid: match[1],
      page: Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1,
      tabId,
      key: `${match[1]}:${Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1}`,
    };
  } catch {
    return null;
  }
}

function getInitialBilibiliTarget() {
  const params = new URLSearchParams(window.location.search);
  return parseBilibiliTarget(params.get("bilibili_url"));
}

export function isVideoScopeMessage(event) {
  return event.source === window.parent &&
    event.origin.startsWith("chrome-extension://");
}

export function WorkspaceVideoScopeEmbed() {
  const controller = useWorkspaceController();
  const page = buildWorkspacePageModel(controller);
  const [target, setTarget] = useState(getInitialBilibiliTarget);
  const requestedTargetKeyRef = useRef(null);
  const selectedTargetKeyRef = useRef(null);
  const [error, setError] = useState(null);
  const [seekError, setSeekError] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatDraft, setChatDraft] = useState("");

  useEffect(() => {
    function handleVideoContext(event) {
      if (!isVideoScopeMessage(event)) {
        return;
      }
      if (event.data?.type === "vsummary:seek-result") {
        setSeekError(event.data.ok === true ? null : event.data.error ?? "无法定位 Bilibili 播放器。");
        return;
      }
      if (event.data?.type !== "vsummary:set-video-context") {
        return;
      }
      const nextTarget = parseBilibiliTarget(event.data.context?.url, event.data.context?.tabId ?? null);
      if (!nextTarget) {
        return;
      }
      setTarget((currentTarget) => (
        currentTarget?.key === nextTarget.key && currentTarget?.sourceUrl === nextTarget.sourceUrl
          ? currentTarget
          : nextTarget
      ));
    }

    window.addEventListener("message", handleVideoContext);
    if (window.parent !== window) {
      window.parent.postMessage({ type: "vsummary:video-scope-ready" }, "*");
    }
    return () => window.removeEventListener("message", handleVideoContext);
  }, []);

  useEffect(() => {
    setChatOpen(false);
    setChatDraft("");
    setSeekError(null);
  }, [target?.key]);

  function seekBilibiliVideo({ seconds } = {}) {
    if (!Number.isFinite(seconds) || window.parent === window) {
      return;
    }
    window.parent.postMessage({
      type: "vsummary:seek",
      seconds,
      autoplay: true,
    }, "*");
  }

  useEffect(() => {
    if (!target || !target.bvid || !controller.state.library || error?.key === target.key) {
      return;
    }
    const inbox = controller.state.library.series?.find((series) => series.id === BILIBILI_INBOX_SERIES_ID);
    if (!inbox) {
      setError({ key: target.key, message: "当前 VSummary 版本不支持 B站导入，请升级主程序。" });
      return;
    }
    const video = inbox.videos.find((item) => item.sourceId === target.bvid && item.itemIndex === target.page);
    if (!video) {
      if (requestedTargetKeyRef.current !== target.key) {
        requestedTargetKeyRef.current = target.key;
        controller.onResolveSeriesVideo("bilibili", target.sourceUrl, BILIBILI_INBOX_SERIES_ID).catch((resolveError) => {
          setError({
            key: target.key,
            message: resolveError instanceof Error ? resolveError.message : "导入当前 Bilibili 视频失败。",
          });
        });
      }
      return;
    }
    if (selectedTargetKeyRef.current !== target.key) {
      selectedTargetKeyRef.current = target.key;
      controller.onSelectVideo(BILIBILI_INBOX_SERIES_ID, video.id);
    }
  }, [controller, error?.key, target]);

  if (error && error.key === target?.key) {
    return <WorkspaceStateBlock eyebrow="VSummary" title="无法打开视频工作区" description={error.message} dashed />;
  }
  if (!target || !target.bvid) {
    return <WorkspaceStateBlock eyebrow="VSummary" title="当前页面不支持" description="请在 Bilibili 视频播放页打开此侧边栏。" dashed />;
  }
  const selectedVideoMatchesTarget =
    page.shell.selectedVideo?.sourceId === target.bvid &&
    page.shell.selectedVideo?.itemIndex === target.page;
  if (!page.shell.activeSeries || !selectedVideoMatchesTarget || page.shell.selectedContextType !== "video") {
    return <WorkspaceStateBlock eyebrow="VSummary" title="正在打开视频工作区" description="正在定位当前 Bilibili 视频。" loading />;
  }

  const chatPanelProps = {
    workspaceTitle: page.shell.library?.workspace?.title,
    activeSeries: page.shell.activeSeries,
    selectedVideo: page.shell.selectedVideo,
    selectedContextType: page.shell.selectedContextType,
    selectedToolId: page.shell.state.selectedToolId,
    chatMessages: page.chat.messages,
    chatSessions: page.chat.sessions,
    activeSessionId: page.chat.activeSessionId,
    chatPending: page.chat.pending,
    summaryLocked: page.shell.selectedVideo?.processed !== true,
    contextUsage: page.chat.contextUsage,
    contextUsageLoading: page.chat.contextUsageLoading,
    ragModels: page.generation.ragModels,
    knowledgeMemorySnapshot: page.shell.state.knowledgeMemorySnapshot,
    draft: chatDraft,
    onDraftChange: setChatDraft,
    onSelectChatSession: page.chat.selectChatSession,
    onOpenSeekReference: (reference) => {
      page.chat.openSeekReference(reference);
      seekBilibiliVideo(reference);
    },
    onOpenCitationReference: (reference) => {
      page.chat.openCitationReference(reference);
      seekBilibiliVideo(reference);
    },
    onSubmitChat: page.chat.submit,
    onCancelChat: page.chat.cancel,
  };

  return (
    <div className="relative h-screen">
      {seekError ? (
        <div className="absolute inset-x-4 top-4 z-20 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 shadow-sm" role="alert">
          {seekError}
        </div>
      ) : null}
      <WorkspaceVideoScopePane
        page={page}
        onProcessLinkedVideo={controller.onProcessLinkedVideo}
        onOpenChat={() => setChatOpen(true)}
        onExternalSeek={seekBilibiliVideo}
      />
      {page.generation.showOverlay && page.generation.snapshot ? (
        <WorkspaceGenerationOverlay
          generationProgress={page.generation.progress}
          generationSnapshot={page.generation.snapshot}
          onCancel={controller.onCancelGeneration}
        />
      ) : null}
      <ChatDrawer
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        fullWidth
        {...chatPanelProps}
      />
    </div>
  );
}
