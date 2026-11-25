import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";

/**
 * First-run notice on the empty library: shown while no model API key is saved.
 * Re-checks whenever the settings panel closes, so it disappears right after the key is saved.
 */
export function LocalSetupBanner({ api, settingsOpen, onOpenSettings }) {
  const [missingKey, setMissingKey] = useState(false);

  useEffect(() => {
    if (settingsOpen) return undefined;
    let live = true;
    api
      .loadProviderSettings()
      .then((settings) => {
        if (live) setMissingKey(!settings?.hasOpenaiApiKey);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [api, settingsOpen]);

  if (!missingKey) return null;

  return (
    <section
      aria-label="模型配置提示"
      className="mb-8 flex items-center gap-3 rounded-2xl border border-warning-border/80 bg-warning-subtle/70 px-4 py-3 text-left"
    >
      <KeyRound size={17} className="shrink-0 text-warning" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-strong">尚未配置模型 API Key</p>
        <p className="mt-0.5 text-xs text-subtle">填写 OpenAI 兼容接口的地址和 Key 后即可处理视频。</p>
      </div>
      <button
        type="button"
        onClick={onOpenSettings}
        className="shrink-0 rounded-xl border border-line bg-surface px-3.5 py-1.5 text-xs font-semibold text-body transition-colors hover:border-accent/45 hover:text-accent"
      >
        前往设置
      </button>
    </section>
  );
}
