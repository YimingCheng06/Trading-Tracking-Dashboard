"use client";

import { useEffect, useState } from "react";
import {
  getLiveSettings,
  setLiveSettings,
  type IntervalSeconds,
  type LiveSettings,
} from "@/lib/settings";

const INTERVAL_OPTIONS: {
  value: IntervalSeconds;
  label: string;
  hint: string;
}[] = [
  { value: 30, label: "30s", hint: "反馈最活,Yahoo 调用最频" },
  { value: 60, label: "60s", hint: "默认" },
  { value: 120, label: "120s", hint: "省网络" },
  { value: null, label: "Manual", hint: "不自动刷新" },
];

export function LiveDataSettings() {
  const [draft, setDraft] = useState<LiveSettings | null>(null);
  const [saved, setSaved] = useState<LiveSettings | null>(null);
  const [savedNote, setSavedNote] = useState(false);

  useEffect(() => {
    const initial = getLiveSettings();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(initial);
    setSaved(initial);
  }, []);

  if (!draft || !saved) return null;

  const dirty =
    draft.intervalSeconds !== saved.intervalSeconds ||
    draft.includeAfterHours !== saved.includeAfterHours;

  function onSave() {
    setLiveSettings(draft!);
    setSaved(draft);
    setSavedNote(true);
    window.setTimeout(() => setSavedNote(false), 2000);
  }

  function onCancel() {
    setDraft(saved!);
  }

  return (
    <section className="rounded-2xl border border-border bg-surface/60 p-6">
      <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
        Live Data
      </h2>
      <p className="mt-1 text-xs text-muted">
        控制 /positions 与 /pnl 页面的自动刷新行为。
      </p>

      <fieldset className="mt-6">
        <legend className="text-sm font-medium text-foreground">
          Polling frequency
        </legend>
        <div className="mt-3 space-y-2">
          {INTERVAL_OPTIONS.map((opt) => {
            const id = `interval-${opt.value ?? "manual"}`;
            return (
              <label
                key={id}
                htmlFor={id}
                className="flex cursor-pointer items-center gap-3 text-sm text-foreground"
              >
                <input
                  id={id}
                  type="radio"
                  name="intervalSeconds"
                  checked={draft.intervalSeconds === opt.value}
                  onChange={() =>
                    setDraft({ ...draft, intervalSeconds: opt.value })
                  }
                  className="h-4 w-4"
                />
                <span className="font-medium">{opt.label}</span>
                <span className="text-xs text-muted">— {opt.hint}</span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <label className="mt-6 flex cursor-pointer items-start gap-3 text-sm text-foreground">
        <input
          type="checkbox"
          checked={draft.includeAfterHours}
          onChange={(e) =>
            setDraft({ ...draft, includeAfterHours: e.target.checked })
          }
          className="mt-0.5 h-4 w-4"
        />
        <span>
          Include after-hours / pre-market
          <span className="ml-2 text-xs text-muted">
            (默认关闭。打开后,周一至周五全天轮询;周末始终不轮询)
          </span>
        </span>
      </label>

      <div className="mt-6 flex items-center justify-end gap-3">
        {savedNote && (
          <span className="text-xs text-up">已保存</span>
        )}
        <button
          type="button"
          onClick={onCancel}
          disabled={!dirty}
          className="rounded-xl border border-border bg-surface px-4 py-2 text-sm text-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-rail-deep transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          保存
        </button>
      </div>
    </section>
  );
}
