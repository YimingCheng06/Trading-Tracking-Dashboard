/**
 * 判定给定时刻是否在美股常规交易时段(US/Eastern Mon–Fri 09:30–16:00)。
 *
 * 用 Intl.DateTimeFormat 把 UTC Date 转 ET,避免引入 tz 库。无假日日历 —— US
 * holidays 当作交易日(MVP scope,会拉到 stale 价,徽章不标记)。
 */
export function isUsMarketOpen(now: Date): boolean {
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

  if (weekday === "Sat" || weekday === "Sun") return false;

  // Intl returns "24" for midnight in some locales; normalize.
  const hour = Number(hourStr) % 24;
  const minute = Number(minStr);
  const minutes = hour * 60 + minute;
  const OPEN = 9 * 60 + 30; // 09:30 ET
  const CLOSE = 16 * 60;    // 16:00 ET
  return minutes >= OPEN && minutes < CLOSE;
}
