import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowLeft,ExternalLink,Sparkles} from 'lucide-react';
import {MindmapCanvas,WorkspaceMarkdownMessage} from '@alpha03123/vsummary-workspace-ui';
import {formatDuration} from './ExampleCards';

// Example data is bundled per video and only loaded when its page opens.
const LOADERS=import.meta.glob(['./data/*.json','!./data/index.json']);
const TABS=[{id:'summary',label:'AI 概括'},{id:'chapters',label:'章节'},{id:'mindmap',label:'导图'},{id:'cards',label:'知识卡片'},{id:'transcript',label:'逐字稿'}];
const CARD_KINDS={concept:'概念',method:'方法',fact:'事实',example:'例子',insight:'观点',question:'问题'};

function timeRange(start,end){return `${formatDuration(start)} – ${formatDuration(end)}`;}

function SummaryTab({example,onOpenCitation}){
 return <div className="flex flex-col gap-5">
  {example.core_problem&&<div className="rounded-2xl border border-line bg-muted p-5">
   <p className="mb-1.5 text-xs font-semibold text-faint">核心问题</p>
   <p className="text-base leading-relaxed text-body">{example.core_problem}</p>
  </div>}
  {example.key_takeaways.length>0&&<div>
   <p className="mb-2 text-xs font-semibold text-faint">关键收获</p>
   <ul className="flex flex-col gap-2">{example.key_takeaways.map(item=><li key={item} className="flex gap-2.5 text-sm leading-relaxed text-body"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"/>{item}</li>)}</ul>
  </div>}
  <article className="markdown-body text-sm leading-7 text-body">
   <WorkspaceMarkdownMessage content={example.ai_summary.content} citations={example.ai_summary.citations} onOpenCitationReference={onOpenCitation} onOpenTranscriptAtTime={onOpenCitation}/>
  </article>
  <p className="text-xs text-faint">点 [1]、[2] 可跳到逐字稿原文。</p>
 </div>;
}

function ChaptersTab({example}){
 return <ol className="flex flex-col gap-4">{example.chapters.map((chapter,index)=><li key={chapter.title} className="flex flex-col gap-4 rounded-2xl border border-line p-4 sm:flex-row">
  {chapter.image_url&&<img src={chapter.image_url} alt={`${chapter.title} 截图`} loading="lazy" className="aspect-video w-full shrink-0 rounded-xl object-cover sm:w-56"/>}
  <div className="min-w-0">
   <p className="text-xs font-semibold text-faint">第 {index+1} 章 · {timeRange(chapter.start_seconds,chapter.end_seconds)}</p>
   <h3 className="mt-1 text-base font-semibold text-strong">{chapter.title}</h3>
   <p className="mt-1.5 text-sm leading-relaxed text-subtle">{chapter.summary}</p>
   {chapter.key_points.length>0&&<ul className="mt-2 flex flex-col gap-1">{chapter.key_points.map(point=><li key={point} className="text-sm leading-relaxed text-subtle before:mr-2 before:text-ghost before:content-['·']">{point}</li>)}</ul>}
  </div>
 </li>)}</ol>;
}

function MindmapTab({example,onOpenNode}){
 const markmapRef=useRef(null);
 return <div>
  <div className="relative h-[60dvh] min-h-[360px] overflow-hidden rounded-2xl border border-line bg-surface">
   <MindmapCanvas root={example.mindmap} markmapRef={markmapRef} onSelectNode={node=>onOpenNode({seconds:node.start_seconds})}/>
  </div>
  <p className="mt-2 text-xs text-faint">可拖动和缩放。点节点文字跳到逐字稿，点圆点折叠分支。</p>
 </div>;
}

function CardsTab({example}){
 if(!example.knowledge_cards.length)return <p className="text-sm text-faint">这个视频没有知识卡片。</p>;
 return <div className="grid gap-4 md:grid-cols-2">{example.knowledge_cards.map(card=><article key={card.id} className="flex flex-col gap-2 rounded-2xl border border-line p-5">
  <span className="w-fit rounded-md bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">{CARD_KINDS[card.kind]??'要点'}</span>
  <h3 className="text-base font-semibold leading-snug text-strong">{card.title}</h3>
  <p className="text-sm leading-relaxed text-subtle">{card.summary}</p>
  {card.details&&<details className="text-sm leading-relaxed text-subtle"><summary className="cursor-pointer text-xs font-semibold text-faint hover:text-accent">展开详细说明</summary><p className="mt-2">{card.details}</p></details>}
  {card.tags?.length>0&&<div className="mt-auto flex flex-wrap gap-1.5 pt-1">{card.tags.map(tag=><span key={tag} className="rounded-md bg-soft px-2 py-0.5 text-xs text-faint">{tag}</span>)}</div>}
 </article>)}</div>;
}

function TranscriptTab({example,focusSeconds}){
 const focusIndex=useMemo(()=>focusSeconds==null?-1:example.transcript.findIndex(segment=>segment.end_seconds>focusSeconds),[example,focusSeconds]);
 const focusRef=useRef(null);
 useEffect(()=>{focusRef.current?.scrollIntoView({block:'center',behavior:'smooth'});},[focusIndex]);
 return <ol className="flex flex-col">{example.transcript.map((segment,index)=><li key={segment.start_seconds} ref={index===focusIndex?focusRef:null}
  className={`flex gap-4 rounded-xl px-3 py-2 text-sm leading-relaxed transition-colors ${index===focusIndex?'bg-accent/10 text-strong':'text-body'}`}>
  <span className="w-12 shrink-0 pt-0.5 font-mono text-xs text-faint">{formatDuration(segment.start_seconds)}</span>
  <span>{segment.text}</span>
 </li>)}</ol>;
}

/**
 * A read-only processed example, opened from the empty library's sample cards. It is a layer over the
 * workspace (which keeps applying the theme underneath); closing it just clears the hash.
 */
export default function ExamplePage({slug,onClose}){
 const [example,setExample]=useState(null),[missing,setMissing]=useState(false);
 const [tab,setTab]=useState('summary'),[focusSeconds,setFocusSeconds]=useState(null);
 useEffect(()=>{
  setExample(null);setMissing(false);setTab('summary');setFocusSeconds(null);
  const load=LOADERS[`./data/${slug}.json`];
  if(!load){setMissing(true);return;}
  load().then(module=>setExample(module.default));
 },[slug]);
 useEffect(()=>{
  const onKey=event=>{if(event.key==='Escape')onClose();};
  window.addEventListener('keydown',onKey);
  return ()=>window.removeEventListener('keydown',onKey);
 },[onClose]);
 const openCitation=reference=>{setFocusSeconds(reference?.seconds??null);setTab('transcript');};

 return <main className="fixed inset-0 z-[70] overflow-y-auto bg-canvas text-strong" role="dialog" aria-modal="true" aria-label="示例">
  <header className="sticky top-0 z-20 border-b border-line/80 bg-surface/85 backdrop-blur">
   <div className="mx-auto flex max-w-4xl items-center px-5 py-3">
    <button type="button" onClick={onClose} className="inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm font-semibold text-subtle transition-colors hover:bg-soft hover:text-strong"><ArrowLeft size={16}/>返回</button>
   </div>
  </header>
  <div className="mx-auto max-w-4xl px-5 pb-16 pt-8">
   {missing?<p className="text-sm text-faint">没有找到这个示例。</p>
   :!example?<p className="text-sm text-faint">正在加载示例…</p>
   :<>
    <div className="flex flex-wrap items-center gap-2">
     <span className="rounded-full bg-softer/70 px-2.5 py-0.5 text-xs font-semibold text-subtle">示例</span>
     <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-0.5 text-xs font-semibold text-accent"><Sparkles size={12}/>AI 生成</span>
    </div>
    <h1 className="mt-3 text-2xl font-bold leading-snug">{example.title}</h1>
    <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-faint">
     <span>{formatDuration(example.duration_seconds)}</span>
     {example.source_url&&<a href={example.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-accent hover:underline">原视频<ExternalLink size={13}/></a>}
    </p>
    {example.one_sentence_summary&&<p className="mt-4 text-base leading-relaxed text-body">{example.one_sentence_summary}</p>}
    <nav role="tablist" className="mt-6 flex gap-1 overflow-x-auto border-b border-line">
     {TABS.map(option=><button key={option.id} type="button" role="tab" aria-selected={tab===option.id} onClick={()=>setTab(option.id)}
      className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-semibold transition-colors ${tab===option.id?'border-accent text-strong':'border-transparent text-faint hover:text-body'}`}>{option.label}</button>)}
    </nav>
    <div className="mt-6">
     {tab==='summary'&&<SummaryTab example={example} onOpenCitation={openCitation}/>}
     {tab==='chapters'&&<ChaptersTab example={example}/>}
     {tab==='mindmap'&&<MindmapTab example={example} onOpenNode={openCitation}/>}
     {tab==='cards'&&<CardsTab example={example}/>}
     {tab==='transcript'&&<TranscriptTab example={example} focusSeconds={focusSeconds}/>}
    </div>
   </>}
  </div>
 </main>;
}
