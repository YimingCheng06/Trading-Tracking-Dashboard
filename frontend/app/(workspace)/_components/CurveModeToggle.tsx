"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import type { CurveMode } from "@/lib/api";

const MODES: { value: CurveMode; label: string }[] = [
  { value: "A", label: "Mode A · TWR" },
  { value: "B", label: "Mode B · Net deposits" },
];

/**
 * 净值曲线口径切换。改 URL `?mode=`,保留 `?account=`。
 */
export function CurveModeToggle({ mode }: { mode: CurveMode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function select(next: CurveMode) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("mode", next);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="inline-flex rounded-xl border border-border bg-surface p-1">
      {MODES.map((m) => {
        const active = m.value === mode;
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => select(m.value)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-accent-soft text-accent"
                : "text-muted hover:text-foreground"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
