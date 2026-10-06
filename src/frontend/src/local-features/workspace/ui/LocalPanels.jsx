import React from 'react';
import {WorkspaceSettingsPanel} from './WorkspaceSettingsPanel';
import {WorkspaceUsagePage} from '@alpha03123/vsummary-workspace-ui';
import {WorkspaceImportModal} from './WorkspaceImportModal';
export function LocalSettingsPanel({page}){const {shell:{state,ui},generation,actions}=page;return (<WorkspaceSettingsPanel
                  ui={ui}
                  initialTab={state.settingsPanelInitialTab}
                  fasterWhisperModels={generation.fasterWhisperModels}
                  fasterWhisperModelsLoading={generation.fasterWhisperModelsLoading}
                  ragModels={generation.ragModels}
                  ragModelsLoading={generation.ragModelsLoading}
                  downloadingRagModelKey={generation.downloadingRagModelKey}
                  downloadingModelId={generation.downloadingModelId}
                  modelDownloadsById={generation.modelDownloadsById}
                  modelDownloadStatus={generation.modelDownloadStatus}
                  modelDownloadProgress={generation.modelDownloadProgress}
                  modelDownloadErrorModelId={generation.modelDownloadErrorModelId}
                  modelDownloadError={generation.modelDownloadError}
                  onChangeSetting={actions.changeSetting}
                  onSaveProviderSettings={actions.saveProviderSettings}
                  onSelectProviderModel={actions.selectProviderModel}
                  onDiscoverProviderModels={actions.discoverProviderModels}
                  onSaveApiKey={actions.saveApiKey}
                  onSaveAsrSettings={actions.saveAsrSettings}
                  onRevealAsrApiKey={actions.revealAsrApiKey}
                  onTestAsrConnection={actions.testAsrConnection}
                  onRevealOpenaiApiKey={actions.revealOpenaiApiKey}
                  onTestProviderConnection={actions.testProviderConnection}
                  onDownloadFasterWhisperModel={actions.downloadFasterWhisperModel}
                  onCancelFasterWhisperModelDownload={actions.cancelFasterWhisperModelDownload}
                  onDownloadRagModel={actions.downloadRagModel}
                  onCancelRagModelDownload={actions.cancelRagModelDownload}
                  onCheckApplicationUpdate={actions.checkApplicationUpdate}
                  onScheduleApplicationUpdate={actions.scheduleApplicationUpdate}
                  onSelectLegacyMigrationSource={actions.selectLegacyMigrationSource}
                  onInspectLegacyMigration={actions.inspectLegacyMigration}
                  onCreateLegacyMigrationRun={actions.createLegacyMigrationRun}
                  onStartLegacyMigrationRun={actions.startLegacyMigrationRun}
                  onLoadLegacyMigrationRun={actions.loadLegacyMigrationRun}
                  onLoadLatestLegacyMigrationRun={actions.loadLatestLegacyMigrationRun}
                  onCancelLegacyMigrationRun={actions.cancelLegacyMigrationRun}
                  onResetSettings={actions.resetSettings}
                  onOpenUsagePage={() => {
                    actions.closeSettingsPanel();
                    actions.openUsagePage();
                  }}
                  onClose={actions.closeSettingsPanel}
                />);}
export function LocalUsagePanel({page}){const {shell:{state,ui},generation,actions}=page;return (<WorkspaceUsagePage
                  usage={generation.providerUsage}
                  range={generation.providerUsageRange}
                  loading={generation.providerUsageLoading}
                  error={generation.providerUsageError}
                  onChangeRange={actions.changeProviderUsageRange}
                  onClose={actions.closeUsagePage}
                />);}
export function LocalImportPanel({page, request: importModalState, onClose}){const {shell:{state,ui},generation,actions}=page;return (<WorkspaceImportModal
          mode={importModalState.mode}
          targetSeriesId={importModalState.targetSeriesId ?? null}
          targetSeriesTitle={importModalState.targetSeriesTitle ?? ""}
          onClose={onClose}
          onResolveSeries={async (provider, url, selection) => actions.resolveLinkedSeries(provider, url, selection)}
          onResolveVideo={async (provider, url, targetSeriesId) => (
            targetSeriesId
              ? actions.resolveSeriesVideo(provider, url, targetSeriesId)
              : actions.resolvePlaygroundVideo(provider, url)
          )}
          onInitExternalCookie={actions.initExternalCookie}
          onLoadChaoxingStatus={actions.loadChaoxingStatus}
          onInitChaoxing={actions.initChaoxing}
          onCancelChaoxingInit={actions.cancelChaoxingInit}
          onCancelChaoxingImport={actions.cancelChaoxingImport}
          onLoadChaoxingCourses={actions.loadChaoxingCourses}
          onImportChaoxingCourse={actions.importChaoxingCourse}
           onSelectLocalMedia={actions.selectLocalMedia}
           onImportLocalSeries={async (seriesTitle, sourcePaths, storageMode) => actions.importLocalSeries(seriesTitle, sourcePaths, storageMode)}
           onImportSeriesVideos={async (seriesId, sourcePaths) => actions.importSeriesVideos(seriesId, sourcePaths)}
           onImportLocalPlaygroundVideos={async (sourcePaths) => actions.importLocalPlaygroundVideos(sourcePaths)}
        />);}
