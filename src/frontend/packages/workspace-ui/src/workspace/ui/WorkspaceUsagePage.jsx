import {lazy, Suspense} from 'react';
import {motion} from 'framer-motion';
import {BarChart3, X} from 'lucide-react';
import {twMerge} from 'tailwind-merge';
import {popScaleVariant} from '../../lib/animations';
import {WorkspaceStateBlock} from './shared/WorkspaceStateBlock';

const AnalyticsContent=lazy(()=>import('./WorkspaceUsageAnalytics').then(module=>({default:module.WorkspaceUsageAnalytics})));

/** Composable analytics with its own lazy chart loading boundary. */
export function WorkspaceUsageAnalytics(props) {
 return <Suspense fallback={<WorkspaceStateBlock loading title="正在读取用量统计" className="mt-0 min-h-0 py-12"/>}>
  <AnalyticsContent {...props}/>
 </Suspense>;
}

/** Shared usage surface. Hosts can supply quota content or use the token analytics view. */
export function WorkspaceUsagePage({usage,range,loading,error,onChangeRange,onClose,title='API 用量统计',eyebrow='Analytics',icon=<BarChart3 size={20} strokeWidth={2.2}/>,closeLabel='关闭面板',className,bodyClassName,children}) {
 return <motion.section variants={popScaleVariant} initial="initial" animate="animate" exit="exit"
  className={twMerge('workspace-panel rounded-[2rem] shadow-2xl border w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden pointer-events-auto',className)} aria-label={title}>
  <header className="flex shrink-0 items-center justify-between gap-4 border-b border-stone-200/60 px-6 py-5 dark:border-white/5">
   <div className="flex min-w-0 items-center gap-4">
    {icon&&<div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">{icon}</div>}
    <div className="min-w-0">
     {eyebrow&&<p className="text-[10px] font-bold uppercase tracking-widest text-accent">{eyebrow}</p>}
     <h2 className="text-xl font-bold tracking-tight text-stone-900 dark:text-stone-100">{title}</h2>
    </div>
   </div>
   {onClose&&<button type="button" onClick={onClose} aria-label={closeLabel} className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-stone-100 text-stone-600 transition-colors hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"><X size={18}/></button>}
  </header>
  <div className={twMerge('min-h-0 flex-1 overflow-y-auto px-6 pb-6',bodyClassName)}>
   {children!==undefined?children:
    <WorkspaceUsageAnalytics usage={usage} range={range} loading={loading} error={error} onChangeRange={onChangeRange}/>
   }
  </div>
 </motion.section>;
}
