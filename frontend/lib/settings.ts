/**
 * Live data 设置 —— 浏览器 localStorage 单一存储。
 * 同一原点的多 tab 通过原生 `storage` 事件自动同步;同 tab 内手动派发
 * `livesettings` CustomEvent 让本 tab 也立刻响应。
 */

export type IntervalSeconds = 30 | 60 | 120 | null;

export type LiveSettings = {
  intervalSeconds: IntervalSeconds; // null = manual
  includeAfterHours: boolean;
};

const KEY = "liveDataSettings";
const EVENT = "livesettings";

const DEFAULTS: LiveSettings = {
  intervalSeconds: 60,
  includeAfterHours: false,
};

const VALID_INTERVALS = new Set<number | null>([30, 60, 120, null]);

function isLiveSettings(v: unknown): v is LiveSettings {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    (o.intervalSeconds === null || VALID_INTERVALS.has(o.intervalSeconds as number)) &&
    typeof o.includeAfterHours === "boolean"
  );
}

export function getLiveSettings(): LiveSettings {
  if (typeof window === "undefined") return { ...DEFAULTS };
  const raw = window.localStorage.getItem(KEY);
  if (!raw) return { ...DEFAULTS };
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (isLiveSettings(parsed)) return parsed;
  } catch {
    /* fall through to defaults — corrupted entry */
  }
  return { ...DEFAULTS };
}

export function setLiveSettings(next: LiveSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(next));
  // Same-tab listeners do not get the native `storage` event — dispatch a
  // custom one so polling hooks in the current tab pick up changes too.
  window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
}

export function subscribeLiveSettings(
  callback: (s: LiveSettings) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) callback(getLiveSettings());
  };
  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<LiveSettings>).detail;
    callback(detail ?? getLiveSettings());
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(EVENT, onCustom);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(EVENT, onCustom);
  };
}
