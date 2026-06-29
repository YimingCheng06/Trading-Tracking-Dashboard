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
  { value: 30, label: "30s", hint: "Most responsive; most Yahoo calls" },
  { value: 60, label: "60s", hint: "Default" },
  { value: 120, label: "120s", hint: "Saves bandwidth" },
  { value: null, label: "Manual", hint: "No auto-refresh" },
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
        Controls auto-refresh on /positions and /pnl.
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
            (Off by default. When on, polls extended hours too — the
            weekend window Fri 20:00 ET → Sun 20:00 ET stays closed.)
          </span>
        </span>
      </label>

      <div className="mt-6 flex items-center justify-end gap-3">
        {savedNote && (
          <span className="text-xs text-up">Saved</span>
        )}
        <button
          type="button"
          onClick={onCancel}
          disabled={!dirty}
          className="rounded-xl border border-border bg-surface px-4 py-2 text-sm text-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-rail-deep transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </section>
  );
}
