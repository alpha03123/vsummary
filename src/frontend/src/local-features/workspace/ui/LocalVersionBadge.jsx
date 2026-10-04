import {useEffect,useState} from 'react';
export function LocalVersionBadge({api,onOpenUpdate}){const [versionStatus,setVersionStatus]=useState({version:'Source',state:'source'});useEffect(()=>{let live=true;api.loadApplicationUpdateStatus().then(status=>{if(live)setVersionStatus({version:status.installationKind==='source'?'Source':status.currentVersion,state:status.updateAvailable?'available':status.installationKind==='source'?'source':'current'});});return ()=>{live=false};},[api]);return (        <div className="relative flex items-center gap-1">
        {versionStatus.state === "available" ? (
          <button
            type="button"
            onClick={onOpenUpdate}
            title="发现新版本，打开更新页面"
            aria-label={`发现新版本，当前 ${versionStatus.version}，打开更新页面`}
            className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-accent transition-colors hover:bg-accent/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:border-accent/40 dark:bg-accent/15 dark:hover:bg-accent/20"
          >
            {versionStatus.version}
          </button>
        ) : (
          <span className="rounded-full border border-stone-200/80 bg-stone-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400">
            {versionStatus.version}
          </span>
        )}
        </div>
);}
