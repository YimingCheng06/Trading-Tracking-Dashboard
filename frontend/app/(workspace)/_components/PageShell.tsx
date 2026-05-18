import type { ComponentType, ReactNode, SVGProps } from "react";

/**
 * 数据页统一外壳:页头(分组小标 + 标题 + 副标题 + 图标)+ 主体。
 * 与 PlaceholderPage 视觉一致,但承载真实内容与可选的页头操作区。
 */
export function PageShell({
  group,
  title,
  subtitle,
  icon: Icon,
  action,
  children,
}: {
  group: string;
  title: string;
  subtitle: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-6xl px-10 py-14">
      <header className="flex items-start justify-between gap-8">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
            {group}
          </p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">
            {title}
          </h1>
          <p className="mt-3 max-w-xl text-sm text-muted-strong">
            {subtitle}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {action}
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border/80 bg-surface text-accent"
            aria-hidden
          >
            <Icon width={24} height={24} />
          </div>
        </div>
      </header>
      <div className="mt-10">{children}</div>
    </div>
  );
}
