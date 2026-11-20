import {Play} from 'lucide-react';
import examples from './data/index.json';

export function formatDuration(seconds){
 const total=Math.round(seconds??0);
 return `${Math.floor(total/60)}:${String(total%60).padStart(2,'0')}`;
}

export const EXAMPLE_HASH_PREFIX='#/examples/';

/** Processed sample videos under the start field of an empty library, so a first run has something real to open. */
export function ExampleCards(){
 return <section className="w-full text-left">
  <p className="mb-3 text-sm font-semibold text-faint">示例</p>
  <div className="grid gap-x-5 gap-y-6 sm:grid-cols-3">
   {examples.map(example=><a key={example.slug} href={`${EXAMPLE_HASH_PREFIX}${example.slug}`} className="group flex min-w-0 flex-col outline-none">
    {/* Same card as the library grid, so the samples look like what the user's own videos become. */}
    <span className="relative block aspect-video overflow-hidden rounded-2xl border border-line/80 bg-soft shadow-sm transition-all duration-300 group-hover:-translate-y-0.5 group-hover:shadow-md group-focus-visible:ring-4 group-focus-visible:ring-accent/25">
     {example.cover_url&&<img src={example.cover_url} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"/>}
     <span className="absolute bottom-2.5 right-2.5 inline-flex items-center gap-1 rounded-lg bg-black/70 px-2 py-0.5 text-xs font-semibold tabular-nums text-white backdrop-blur"><Play size={11} fill="currentColor"/>{formatDuration(example.duration_seconds)}</span>
    </span>
    <span className="mt-3 line-clamp-2 text-[15px] font-semibold leading-snug text-strong transition-colors group-hover:text-accent">{example.title}</span>
    <span className="mt-1 text-xs text-faint">{example.counts.chapters} 个章节 · {example.counts.cards} 张知识卡片</span>
   </a>)}
  </div>
 </section>;
}
