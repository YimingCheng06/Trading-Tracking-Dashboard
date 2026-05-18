import type { ReactNode } from "react";

/**
 * 统一空态卡片。tone 控制强调色:
 * - "info" 普通空数据(accent 蓝)
 * - "warn" 后端离线 / 错误(down 红)
 */
export function EmptyState({
  tone = "info",
  title,
  hint,
  action,
}: {
  tone?: "info" | "warn";
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  const dot = tone === "warn" ? "bg-down" : "bg-accent";
  return (
    <section className="rounded-2xl border border-dashed border-border bg-surface/40 p-10">
      <div className="flex items-center gap-3">
        <span className={`inline-flex h-2 w-2 rounded-full ${dot}`} />
        <p className="text-sm font-medium text-muted-strong">{title}</p>
      </div>
      {hint && <p className="mt-3 max-w-md text-sm text-muted">{hint}</p>}
      {action && <div className="mt-6">{action}</div>}
    </section>
  );
}
