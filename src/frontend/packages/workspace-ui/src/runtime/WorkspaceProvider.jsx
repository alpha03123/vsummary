import {createContext, useContext, useEffect, useMemo} from 'react';
import {createWorkspaceDataEffects} from '../workspace/model/useWorkspaceDataEffects';
import {createWorkspaceContentActionFactory} from '../workspace/model/workspaceContentActions';

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({host, children}) {
  if (!host?.api || !host.storage) throw new Error('Workspace host requires an API client and scoped storage.');
  const runtime = useMemo(() => ({
    host, api: host.api,
    useDataEffects: createWorkspaceDataEffects(host.api),
    createContentActions: createWorkspaceContentActionFactory(host.api),
  }), [host]);
  useEffect(() => () => host.api.dispose(), [host]);
  return <WorkspaceContext.Provider value={runtime}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaceRuntime() {
  const runtime=useContext(WorkspaceContext);
  if (!runtime) throw new Error('Workspace components must be rendered inside WorkspaceProvider.');
  return runtime;
}
