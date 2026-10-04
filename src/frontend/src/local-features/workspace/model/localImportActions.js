export function createLocalImportActions({state,dispatch,api,coreApi,contentActions}){
const localWorkspaceApi=api;
const {loadWorkspaceLibrary,subscribeDurableJobProgress}=coreApi;
const {reloadWorkspaceLibrary}=contentActions;
const errorMessage=(error,fallback)=>error instanceof Error?error.message:fallback;
async function onSelectLocalMedia() {
    try {
      return await localWorkspaceApi.selectLocalMedia();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "选择本机媒体失败" });
      throw error;
    }
  }
async function onRelinkVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }
    try {
      const result = await localWorkspaceApi.relinkExternalVideo(state.selectedSeriesId, state.selectedVideoId);
      if (result.relinked) {
        await reloadWorkspaceLibrary();
      }
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "重新链接媒体失败" });
    }
  }
async function onImportLocalSeries(seriesTitle, sourcePaths, storageMode) {
    try {
      const rawSeries = await localWorkspaceApi.importLocalSeries(seriesTitle, sourcePaths, storageMode);
      await reloadWorkspaceLibrary();
      return rawSeries;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入本地系列失败" });
      throw error;
    }
  }
async function onInitExternalCookie(provider, options = {}) {
    try {
      return await localWorkspaceApi.initExternalCookie(provider, options);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "获取平台 Cookie 失败" });
      throw error;
    }
  }
async function onLoadChaoxingStatus() {
    try {
      return await localWorkspaceApi.loadChaoxingStatus();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星状态失败" });
      throw error;
    }
  }
async function onInitChaoxing(options = {}) {
    try {
      return await localWorkspaceApi.initChaoxing(options);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "超星初始化失败" });
      throw error;
    }
  }
async function onCancelChaoxingInit() {
    try {
      await localWorkspaceApi.cancelChaoxingInit();
    } catch {
      // 取消是清理动作，失败时不覆盖用户当前操作反馈。
    }
  }
async function onLoadChaoxingCourses() {
    try {
      return await localWorkspaceApi.loadChaoxingCourses();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星课程失败" });
      throw error;
    }
  }
async function onImportChaoxingCourse(courseKey, onProgress = null, options = {}) {
    try {
      const task = await localWorkspaceApi.importChaoxingCourse(courseKey);
      if (!task.jobId) {
        throw new Error("超星导入任务未返回 job_id");
      }
      options.onTaskStarted?.(task);
      return await new Promise((resolve, reject) => {
        let unsubscribe = null;
        unsubscribe = subscribeDurableJobProgress(task.jobId, async (snapshot) => {
          onProgress?.(snapshot);
          if (snapshot.status === "completed") {
            unsubscribe?.();
            const library = await reloadWorkspaceLibrary();
            const importedSeries = library?.series?.find((series) => series.id === task.seriesId);
            resolve(importedSeries ?? { title: "超星课程", videos: [] });
          }
          if (snapshot.status === "failed") {
            unsubscribe?.();
            reject(new Error(snapshot.error || "导入超星课程失败"));
          }
          if (snapshot.status === "cancelled") {
            unsubscribe?.();
            reject(new Error(snapshot.detail || "超星课程导入已取消"));
          }
        });
      });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入超星课程失败" });
      throw error;
    }
  }
async function onCancelChaoxingImport(jobId) {
    if (!jobId) {
      return;
    }
    try {
      await localWorkspaceApi.cancelChaoxingImport(jobId);
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "取消超星课程导入失败" });
      throw error;
    }
  }
async function onImportLocalPlaygroundVideos(sourcePaths) {
    try {
      const rawVideos = await localWorkspaceApi.importLocalPlaygroundVideos(sourcePaths);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入 Playground 媒体失败" });
      throw error;
    }
  }
async function onImportSeriesVideos(seriesId, sourcePaths) {
    try {
      const rawVideos = await localWorkspaceApi.importLocalSeriesVideos(seriesId, sourcePaths);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "向系列导入媒体失败" });
      throw error;
    }
  }
return {onSelectLocalMedia,onRelinkVideo,onImportLocalSeries,onInitExternalCookie,onLoadChaoxingStatus,onInitChaoxing,onCancelChaoxingInit,onLoadChaoxingCourses,onImportChaoxingCourse,onCancelChaoxingImport,onImportLocalPlaygroundVideos,onImportSeriesVideos};
}
