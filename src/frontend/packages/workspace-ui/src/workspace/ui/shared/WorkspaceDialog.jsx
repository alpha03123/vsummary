import {useId,useRef} from 'react';
import {createPortal} from 'react-dom';
import {AnimatePresence,motion} from 'framer-motion';
import {X} from 'lucide-react';
import {twMerge} from 'tailwind-merge';
import {useFocusTrap} from '../../../shared/lib/useFocusTrap';

/** Dialog surface shared by confirmation, rename and host account forms. */
export function WorkspaceDialog({
  open,title,description,icon,eyebrow,header,align='start',
  className,headerClassName,iconClassName,backdropClassName,
  pending=false,onClose,onSubmit,showClose=Boolean(onClose),closeLabel='关闭',children,footer,
}) {
  const id=useId(),ref=useRef(null),backdrop=useRef(false);
  useFocusTrap(ref,open);
  const Panel=onSubmit?motion.form:motion.div;
  return createPortal(<AnimatePresence>{open&&<motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
    className={twMerge('fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm',backdropClassName)}
    onPointerDown={event=>{backdrop.current=event.button===0&&event.target===event.currentTarget;}}
    onPointerUp={event=>{if(backdrop.current&&event.target===event.currentTarget&&!pending)onClose?.();backdrop.current=false;}}>
    <Panel ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} initial={{opacity:0,scale:0.96,y:12}} animate={{opacity:1,scale:1,y:0}} exit={{opacity:0,scale:0.96,y:12}}
      transition={{type:'spring',stiffness:360,damping:28}} className={twMerge('workspace-panel relative w-full max-w-md rounded-[2rem] border p-6 shadow-2xl',className)}
      onKeyDown={event=>{if(event.key==='Escape'&&!pending){event.preventDefault();onClose?.();}}}
      onSubmit={onSubmit?event=>{event.preventDefault();if(!pending)onSubmit(event);}:undefined}>
      {showClose&&onClose&&<button type="button" onClick={onClose} disabled={pending} aria-label={closeLabel} className="absolute right-4 top-4 rounded-xl p-2 text-stone-500 transition-colors hover:bg-stone-100 disabled:opacity-50 dark:text-stone-400 dark:hover:bg-neutral-800"><X size={18}/></button>}
      {header!==undefined?<><h3 id={id} className="sr-only">{title}</h3>{header}</>:<div className={twMerge('flex items-start gap-4',showClose&&onClose&&align!=='center'&&'pr-8',align==='center'&&'flex-col items-center text-center',headerClassName)}>{icon&&<div className={twMerge('flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-accent/20 bg-accent/10 text-accent',iconClassName)}>{icon}</div>}
        <div className="min-w-0 flex-1">{eyebrow&&<p className="text-xs font-semibold text-stone-500 dark:text-stone-400">{eyebrow}</p>}<h3 id={id} className="text-lg font-bold text-stone-900 dark:text-stone-100">{title}</h3>{description&&<p className="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">{description}</p>}</div></div>}
      {children&&<div className="mt-5">{children}</div>}{footer&&<div className="mt-6 flex justify-end gap-3">{footer}</div>}
    </Panel>
  </motion.div>}</AnimatePresence>,document.body);
}
