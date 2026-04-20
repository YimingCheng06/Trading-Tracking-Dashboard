import type { ComponentType, SVGProps } from "react";

/**
 * Placeholder shell for routes that exist structurally but have no
 * implementation yet. Each scaffolded page reuses this with its own
 * title / subtitle / icon so the navigation skeleton is navigable
 * immediately after Phase 0.
 */
export function PlaceholderPage({
  group,
  title,
  subtitle,
  icon: Icon,
  notes,
}: {
  group: string;
  title: string;
  subtitle: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  notes?: string[];
}) {
  return (
    <div className="mx-auto max-w-5xl px-10 py-14">
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
        <div
          className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border/80 bg-surface text-accent"
          aria-hidden
        >
          <Icon width={24} height={24} />
        </div>
      </header>

      <section className="mt-10 rounded-2xl border border-dashed border-border bg-surface/40 p-8">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-accent" />
          <p className="text-sm font-medium text-muted-strong">
            Scaffolded · implementation arrives in Phase 1
          </p>
        </div>
        {notes && notes.length > 0 && (
          <ul className="mt-6 space-y-2 text-sm text-muted">
            {notes.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="text-accent">·</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
