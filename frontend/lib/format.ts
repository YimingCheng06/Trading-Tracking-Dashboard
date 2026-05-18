/** 后端 Decimal 字段可能是 string 或 number;统一转 number。 */
export function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** USD 货币格式,带千位分隔与两位小数。null → "—"。 */
export function fmtMoney(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** 一般数量格式,最多 4 位小数。null → "—"。 */
export function fmtNum(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

/** 百分比:输入为分数(0.123 → "12.30%")。null → "—"。 */
export function fmtPct(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

/** ISO 日期/时间 → "YYYY-MM-DD"。 */
export function fmtDate(iso: string): string {
  return iso.slice(0, 10);
}

/** 盈亏着色 class:正绿、负红、零/空 muted。 */
export function pnlClass(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null || n === 0) return "text-muted-strong";
  return n > 0 ? "text-up" : "text-down";
}
