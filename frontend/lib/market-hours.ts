/**
 * US/Eastern session predicates.
 *
 * `isUsMarketOpen` — regular session, Mon–Fri 09:30–16:00 ET.
 * `isUsMarketSessionClosed` — the "no session at all" window when even
 * extended-hours trading is unavailable: Friday 20:00 ET through
 * Sunday 20:00 ET. Used to force the badge to "Market closed" regardless
 * of the after-hours toggle.
 *
 * Anything not in those two predicates is an extended session (pre-market,
 * after-hours, or overnight) — only polled when the after-hours toggle is on.
 *
 * Uses Intl.DateTimeFormat to convert a UTC Date to ET parts, avoiding a tz
 * library. No US holiday calendar (MVP scope).
 */

type EtParts = { weekday: string; hour: number; minute: number };

function etParts(now: Date): EtParts {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = fmt.formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  const hourStr = parts.find((p) => p.type === "hour")?.value ?? "00";
  const minStr = parts.find((p) => p.type === "minute")?.value ?? "00";
  // Intl returns "24" for midnight in some locales; normalize.
  const hour = Number(hourStr) % 24;
  const minute = Number(minStr);
  return { weekday, hour, minute };
}

const WEEKEND_BOUNDARY = 20 * 60; // 20:00 ET — Fri close / Sun overnight open

export function isUsMarketSessionClosed(now: Date): boolean {
  const { weekday, hour, minute } = etParts(now);
  const minutes = hour * 60 + minute;
  if (weekday === "Sat") return true;
  if (weekday === "Fri" && minutes >= WEEKEND_BOUNDARY) return true;
  if (weekday === "Sun" && minutes < WEEKEND_BOUNDARY) return true;
  return false;
}

export function isUsMarketOpen(now: Date): boolean {
  const { weekday, hour, minute } = etParts(now);
  if (weekday === "Sat" || weekday === "Sun") return false;
  const minutes = hour * 60 + minute;
  const OPEN = 9 * 60 + 30; // 09:30 ET
  const CLOSE = 16 * 60;    // 16:00 ET
  return minutes >= OPEN && minutes < CLOSE;
}
