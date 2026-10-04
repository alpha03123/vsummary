import {createBrowserTransport,createWorkspaceApi,createScopedStorage} from '@alpha03123/vsummary-workspace-ui';
import {createLocalWorkspaceApi} from '../api/localWorkspaceApi';
import {createLocalWorkspaceEffects} from './model/LocalWorkspaceEffects';
import {createLocalImportActions} from './model/localImportActions';
import {createWorkspaceSettingsActions} from './model/workspaceSettingsActions';
import {defaultLocalUiSettings} from './model/localUiSettings';
import {LocalSettingsPanel,LocalUsagePanel,LocalImportPanel} from './ui/LocalPanels';
import {LocalVersionBadge} from './ui/LocalVersionBadge';

export function createLocalHost() {
  const coreApi=createWorkspaceApi(createBrowserTransport());
  const api=createLocalWorkspaceApi(coreApi);
  return {
    api:coreApi,
    storage:createScopedStorage('vsummary:local-installation'),
    initialUi:defaultLocalUiSettings,
    Effects:createLocalWorkspaceEffects(api),
    panels:{Settings:LocalSettingsPanel,Usage:LocalUsagePanel,Import:LocalImportPanel},
    createActions(context){return {
      ...createWorkspaceSettingsActions({...context,api}),
      ...createLocalImportActions({...context,api}),
    };},
    renderToolbar(controller){return <LocalVersionBadge api={api} onOpenUpdate={()=>controller.onOpenSettingsPanel('update')}/>;},
  };
}
