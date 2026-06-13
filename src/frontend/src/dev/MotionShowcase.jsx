import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

// -- Physics Configurations we discussed --
const springTransition = { type: "spring", stiffness: 350, damping: 25, mass: 0.8 };
const bouncyTransition = { type: "spring", stiffness: 400, damping: 15 }; // Extremely bouncy for comparison

export function MotionShowcase() {
  const [selectedId, setSelectedId] = useState(null);
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [messages, setMessages] = useState([1, 2, 3]);
  const [switchTab, setSwitchTab] = useState("1-4");
  const [switchEffect, setSwitchEffect] = useState("fade");

  // Section 6: Sliding Indicator
  const [activeMenu, setActiveMenu] = useState("1.3 准备环境");
  const menus = ["1.3 准备环境", "1.4 Nacos 配置", "1.5 动手写代码"];

  // Section 7: Pagination
  const [page, setPage] = useState(0);
  const [direction, setDirection] = useState(1);

  const paginate = (newDirection) => {
    setDirection(newDirection);
    setPage((prev) => prev + newDirection);
  };
  
  const paginationVariants = {
    enter: (direction) => ({
      x: direction > 0 ? 50 : -50,
      opacity: 0,
      scale: 0.95
    }),
    center: {
      x: 0,
      opacity: 1,
      scale: 1,
      transition: { duration: 0.3, type: "spring", stiffness: 350, damping: 25 }
    },
    exit: (direction) => ({
      x: direction < 0 ? 50 : -50,
      opacity: 0,
      scale: 0.95,
      transition: { duration: 0.2 }
    })
  };

  const cards = [
    { id: 1, title: "Shared Layout (共享变形)", desc: "点击我，像 App Store 一样展开" },
    { id: 2, title: "Smooth Reorder (平滑重排)", desc: "流式的过渡" },
  ];

  const removeMessage = (id) => {
    setMessages((prev) => prev.filter((m) => m !== id));
  };

  const resetMessages = () => setMessages([1, 2, 3]);

  // Transition variants for Section 5
  const switchVariants = {
    fade: {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0, transition: { duration: 0.15 } }
    },
    slide: {
      initial: { opacity: 0, y: 15 },
      animate: { opacity: 1, y: 0, transition: springTransition },
      exit: { opacity: 0, y: -15, transition: { duration: 0.15 } }
    },
    blur: {
      initial: { opacity: 0, filter: "blur(4px)", scale: 0.98 },
      animate: { opacity: 1, filter: "blur(0px)", scale: 1, transition: springTransition },
      exit: { opacity: 0, filter: "blur(4px)", scale: 0.95, transition: { duration: 0.15 } }
    }
  };

  return (
    <div className="flex flex-col h-screen bg-stone-50 overflow-auto p-10 font-sans gap-12 text-stone-900">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Framer Motion 动效实验室</h1>
          <p className="text-stone-500 mt-2">在这里体验原生系统级高级动效，选好感觉后我们再实装到主页面。</p>
        </div>
        <button 
          onClick={() => window.location.hash = ""} 
          className="px-4 py-2 bg-stone-200 text-stone-800 rounded-lg hover:bg-stone-300 font-semibold"
        >
          返回主页面
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">

        {/* 1. Layout Transition (侧边栏收缩重排) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm">
          <h2 className="text-xl font-bold mb-4">1. 无缝布局重排 (Layout Animations)</h2>
          <p className="text-sm text-stone-500 mb-4">当侧边栏宽度改变时，右侧内容块极其平滑地自动填补空缺，告别闪跳。</p>
          
          <button 
            onClick={() => setSidebarOpen(!isSidebarOpen)}
            className="mb-4 px-4 py-2 bg-stone-900 text-white rounded-lg font-medium active:scale-95 transition-transform"
          >
            Toggle Sidebar
          </button>

          <div className="flex gap-4 h-48 bg-stone-100 p-2 rounded-2xl relative overflow-hidden">
            <motion.div 
              layout
              transition={springTransition}
              className={`${isSidebarOpen ? "w-[120px]" : "w-0"} bg-sky-100 rounded-xl flex items-center justify-center overflow-hidden shrink-0`}
            >
              <span className="text-sky-800 font-bold whitespace-nowrap opacity-50">Sidebar</span>
            </motion.div>
            
            <motion.div 
              layout
              transition={springTransition}
              className="flex-1 bg-white rounded-xl border flex items-center justify-center gap-2 p-4"
            >
              <div className="w-10 h-10 rounded-full bg-stone-200 shrink-0" />
              <div className="flex-1 flex flex-col gap-2">
                <div className="h-4 bg-stone-200 rounded w-full" />
                <div className="h-4 bg-stone-200 rounded w-2/3" />
              </div>
            </motion.div>
          </div>
        </section>

        {/* 2. Shared Layout Transition (共享元素变形) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm">
          <h2 className="text-xl font-bold mb-4">2. 共享元素变幻 (layoutId)</h2>
          <p className="text-sm text-stone-500 mb-4">类似 Apple App Store 的卡片展开。卡片脱离文档流直接“飞”成详情页。</p>
          
          <div className="flex gap-4 h-48 relative">
            {cards.map((card) => (
              <motion.div
                layoutId={`card-container-${card.id}`}
                key={card.id}
                onClick={() => setSelectedId(card.id)}
                transition={springTransition}
                className="flex-1 bg-stone-100 rounded-2xl p-4 cursor-pointer hover:bg-stone-200"
              >
                <motion.h3 layoutId={`card-title-${card.id}`} className="font-bold text-lg">{card.title}</motion.h3>
                <p className="text-xs text-stone-500 mt-2">{card.desc}</p>
              </motion.div>
            ))}

            <AnimatePresence>
              {selectedId && (
                <motion.div
                  layoutId={`card-container-${selectedId}`}
                  transition={springTransition}
                  className="absolute inset-0 bg-stone-900 rounded-[2rem] p-8 text-white z-10 flex flex-col shadow-2xl"
                >
                  <motion.h3 layoutId={`card-title-${selectedId}`} className="font-bold text-2xl mb-4">
                    {cards.find(c => c.id === selectedId).title}
                  </motion.h3>
                  <p className="text-zinc-400">这就叫连续性动效。用户完全能感知到界面的空间从属关系。</p>
                  
                  <motion.button 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1, transition: { delay: 0.1 } }}
                    className="mt-auto self-end bg-white/20 px-4 py-2 rounded-lg backdrop-blur"
                    onClick={() => setSelectedId(null)}
                  >
                    关闭详情
                  </motion.button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </section>

        {/* 3. Exit Animation (平滑离场) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm">
          <div className="flex justify-between items-center mb-4">
             <h2 className="text-xl font-bold">3. 彻底告别生硬销毁 (Exit Animation)</h2>
             <button onClick={resetMessages} className="text-sm text-sky-600 font-semibold hover:underline">Reset</button>
          </div>
          <p className="text-sm text-stone-500 mb-4">点击列表项删除。你甚至能看到剩余的元素优雅地上移填补空缺。</p>
          
          <ul className="flex flex-col gap-2">
            <AnimatePresence mode="popLayout">
              {messages.map((id) => (
                <motion.li
                  key={id}
                  layout
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8, x: -20, transition: { duration: 0.15 } }}
                  transition={springTransition}
                  onClick={() => removeMessage(id)}
                  className="bg-red-50 text-red-800 border border-red-100 p-4 rounded-xl cursor-pointer hover:bg-red-100 font-medium font-mono text-sm"
                >
                  Click to delete message #{id}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </section>

        {/* 4. Drag and Constraints (物理拖拽缓冲) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm overflow-hidden overflow-visible">
          <h2 className="text-xl font-bold mb-4">4. 极度真实的拖拽惯性 (Drag Physics)</h2>
          <p className="text-sm text-stone-500 mb-4">非常适合思维导图画板的交互。试着在这个方框内用力甩动圆形节点，感受回弹停滞！</p>
          
          <motion.div className="h-48 bg-stone-100 rounded-2xl border-2 border-stone-200 border-dashed relative overflow-hidden flex items-center justify-center p-4">
             <motion.div
               drag
               dragConstraints={{ left: -100, right: 100, top: -50, bottom: 50 }}
               whileHover={{ scale: 1.1, cursor: "grab" }}
               whileTap={{ scale: 0.9, cursor: "grabbing" }}
               transition={bouncyTransition}
               className="w-16 h-16 bg-accent rounded-full shadow-lg flex items-center justify-center text-white text-xs font-bold"
             >
                甩我
             </motion.div>
          </motion.div>
        </section>

        {/* 5. Peer-to-Peer Switch (同级平滑切换) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm lg:col-span-2">
          <h2 className="text-xl font-bold mb-2">5. 同级平滑切换 (Peer-to-Peer Switch)</h2>
          <p className="text-sm text-stone-500 mb-6">这就是我们刚刚讨论的场景：在工作区左侧栏切换不同视频时，右侧主体内容的无缝过渡。</p>
          
          <div className="flex gap-4 mb-6">
            <span className="text-sm font-bold text-stone-700 flex items-center mr-2">选择动效风格:</span>
            {["fade", "slide", "blur"].map(effect => (
              <label key={effect} className="flex flex-row items-center gap-2 text-sm cursor-pointer hover:text-sky-600">
                <input type="radio" name="effect" checked={switchEffect === effect} onChange={() => setSwitchEffect(effect)} />
                <span className="uppercase font-mono">{effect}</span>
              </label>
            ))}
          </div>

          <div className="flex flex-col md:flex-row h-72 rounded-2xl border overflow-hidden bg-stone-50">
            {/* Mock Sidebar */}
            <div className="w-full md:w-64 bg-stone-100 border-b md:border-b-0 md:border-r border-stone-200 p-4 flex flex-col gap-2 shrink-0">
              <span className="text-xs font-bold text-stone-500 tracking-widest pl-2 mb-2">VIDEOS LIST</span>
              {["1-4 准备工作", "1-5 安装 Nacos", "1-6 仿 Manus 框架"].map(tab => (
                <button 
                  key={tab} 
                  onClick={() => setSwitchTab(tab)}
                  className={`text-left px-4 py-3 rounded-xl text-sm font-semibold transition-all ${switchTab === tab ? "bg-white shadow-sm border border-stone-200 text-sky-600" : "text-stone-600 hover:bg-stone-200/50"}`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Mock Main Content Area */}
            <div className="flex-1 relative bg-white p-8 flex items-center justify-center overflow-hidden">
               {/* 关键点：mode="wait" 会等待 exit 动画播完再挂载新的。key 属性必不可少，用来让 react 知道组件变了 */}
               <AnimatePresence mode="wait">
                 <motion.div
                   key={switchTab}
                   variants={switchVariants[switchEffect]}
                   initial="initial"
                   animate="animate"
                   exit="exit"
                   className="absolute w-full max-w-md bg-stone-50/50 border border-stone-100 p-8 rounded-2xl text-center"
                 >
                   <div className="w-16 h-16 rounded-full bg-stone-200 mx-auto mb-4" />
                   <h3 className="text-2xl font-bold text-stone-800 mb-2">{switchTab}</h3>
                   <p className="text-stone-500 text-sm">这里是当前视频的详细信息、AI 总结内容等。感受 {switchEffect.toUpperCase()} 退场和进场时的优雅交接。</p>
                 </motion.div>
               </AnimatePresence>
            </div>
          </div>
        </section>

        {/* 6. Active Indicator Slide (平滑选中框过渡) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm">
          <h2 className="text-xl font-bold mb-4">6. 平滑选中框过渡 (Active Indicator)</h2>
          <p className="text-sm text-stone-500 mb-6">点击任意项目。你想要的选中框“不仅是变色，而是丝滑滑过去”的神级效果。</p>
          
          <div className="flex flex-col gap-1 w-full max-w-xs bg-stone-100 p-2 rounded-2xl relative">
            {menus.map((menu) => {
              const isActive = activeMenu === menu;
              return (
                <button
                  key={menu}
                  onClick={() => setActiveMenu(menu)}
                  className={`relative w-full text-left px-4 py-3 rounded-xl text-sm font-bold transition-colors duration-200 z-10 ${
                    isActive ? "text-sky-900" : "text-stone-500 hover:text-stone-800"
                  }`}
                >
                  {/* The secret sauce: An absolutely positioned background with layoutId */}
                  {isActive && (
                    <motion.div
                      layoutId="sidebar-active-bg"
                      transition={springTransition}
                      className="absolute inset-0 bg-white shadow-sm border border-stone-200/50 rounded-xl -z-10"
                    />
                  )}
                  {menu}
                </button>
              );
            })}
          </div>
        </section>

        {/* 7. Pagination View (页码翻页过渡) */}
        <section className="bg-white p-6 rounded-[2rem] border shadow-sm">
          <div className="flex justify-between items-center mb-4">
             <h2 className="text-xl font-bold">7. 立体页码翻页 (Pagination Flip)</h2>
             <div className="flex gap-2">
                <button onClick={() => paginate(-1)} className="p-2 bg-stone-100 hover:bg-stone-200 rounded-full text-stone-800">
                  ←
                </button>
                <button onClick={() => paginate(1)} className="p-2 bg-stone-100 hover:bg-stone-200 rounded-full text-stone-800">
                  →
                </button>
             </div>
          </div>
          <p className="text-sm text-stone-500 mb-6">具有方向感知（向左翻左入，向右翻右入），经常用在全屏图库或章节阅读里。</p>

          <div className="relative h-48 w-full flex items-center justify-center bg-stone-50 rounded-2xl border overflow-hidden">
            <AnimatePresence custom={direction} mode="popLayout">
               <motion.div
                 key={page}
                 custom={direction}
                 variants={paginationVariants}
                 initial="enter"
                 animate="center"
                 exit="exit"
                 className="absolute w-3/4 h-3/4 bg-white border shadow-sm rounded-xl flex items-center justify-center text-4xl font-mono font-bold text-stone-300"
               >
                 PAGE {page}
               </motion.div>
            </AnimatePresence>
          </div>
        </section>

      </div>
    </div>
  );
}
