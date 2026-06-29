/**
 * US/Eastern market-hours predicates.
 *
 * `isUsMarketOpen` — Mon–Fri 09:30–16:00 ET (regular session).
 * `isUsWeekend` — Sat or Sun in ET (used to gate the after-hours toggle:
 * the toggle only enables polling during weekday extended hours; weekends
 * always show "Market closed" since there is no session to track).
 *
 * Uses Intl.DateTimeFormat to convert a UTC Date to ET parts, avoiding
 * a tz library. No US holiday calendar (MVP scope — holidays poll as if
 * open and just return the last close).
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

export function isUsWeekend(now: Date): boolean {
  const { weekday } = etParts(now);
  return weekday === "Sat" || weekday === "Sun";
}

export function isUsMarketOpen(now: Date): boolean {
  const { weekday, hour, minute } = etParts(now);
  if (weekday === "Sat" || weekday === "Sun") return false;
  const minutes = hour * 60 + minute;
  const OPEN = 9 * 60 + 30; // 09:30 ET
  const CLOSE = 16 * 60;    // 16:00 ET
  return minutes >= OPEN && minutes < CLOSE;
}
