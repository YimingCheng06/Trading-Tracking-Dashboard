import { api, type HealthResponse } from "@/lib/api";
import {
  IconTrendingUp,
  IconBriefcase,
  IconSparkLine,
} from "../_components/icons";

export const dynamic = "force-dynamic";

async function getHealth(): Promise<HealthResponse | null> {
  try {
    return await api.health();
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  const health = await getHealth();
  const online = health?.status === "ok";

  return (
    <div className="mx-auto max-w-6xl px-10 py-12">
      <Breadcrumb online={online} />

      <Hero
        base={health?.base_currency ?? "—"}
        online={online}
        environment={health?.environment ?? "unknown"}
      />

      <section className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Metric
          icon={<IconBriefcase width={18} height={18} />}
          label="Total Value"
          value="—"
          sublabel="awaiting data"
          accent="var(--accent)"
        />
        <Metric
          icon={<IconTrendingUp width={18} height={18} />}
          label="Day P&L"
          value="—"
          sublabel="awaiting data"
          accent="var(--up)"
        />
        <Metric
          icon={<IconSparkLine width={18} height={18} />}
          label="Base Currency"
          value={health?.base_currency ?? "—"}
          sublabel={online ? "backend online" : "backend offline"}
          accent={online ? "var(--up)" : "var(--down)"}
        />
      </section>

      <section className="mt-10 rounded-2xl border border-border bg-surface/60 p-6 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
            Phase 0 Health Check
          </h2>
          <StatusDot online={online} />
        </div>
        <pre className="tabular mt-4 overflow-x-auto rounded-lg border border-border/60 bg-rail/60 p-4 text-sm text-foreground/90">
          {JSON.stringify(health ?? { error: "backend unreachable" }, null, 2)}
        </pre>
      </section>
    </div>
  );
}

function Breadcrumb({ online }: { online: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.22em] text-muted">
      <span>Portfolio</span>
      <span className="text-border-strong">/</span>
      <span className="text-muted-strong">Dashboard</span>
      <span className="ml-auto flex items-center gap-2">
        <StatusDot online={online} />
        <span className={online ? "text-up" : "text-down"}>
          {online ? "backend online" : "backend offline"}
        </span>
      </span>
    </div>
  );
}

function Hero({
  base,
  online,
  environment,
}: {
  base: string;
  online: boolean;
  environment: string;
}) {
  return (
    <section className="mt-6 overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-surface via-surface to-rail p-10">
      <p className="text-xs font-medium uppercase tracking-[0.28em] text-muted">
        Portfolio snapshot
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3">
        <h1 className="tabular text-7xl font-semibold tracking-tight">
          <span className="text-muted-strong">—</span>
          <span className="ml-3 text-2xl font-medium text-muted">{base}</span>
        </h1>
        <span
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
            online
              ? "border-up/40 bg-up/10 text-up"
              : "border-down/40 bg-down/10 text-down"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-up" : "bg-down"}`} />
          {environment}
        </span>
      </div>
      <p className="mt-4 max-w-xl text-sm text-muted-strong">
        Phase 0 scaffolding online. Real numbers land once the statement
        importer and IBKR adapter are wired up in Phase 1.
      </p>

      <div className="mt-8 h-1 w-full overflow-hidden rounded-full bg-border/40">
        <div
          className="h-full w-[8%] rounded-full"
          style={{
            background:
              "linear-gradient(90deg, var(--accent) 0%, var(--up) 100%)",
          }}
        />
      </div>
      <p className="mt-2 flex justify-between text-[10px] uppercase tracking-[0.18em] text-muted">
        <span>Phase 0 · shell</span>
        <span>Phase 1 · import</span>
        <span>Phase 2 · live</span>
        <span>Phase 3 · intelligence</span>
      </p>
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
  sublabel,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sublabel: string;
  accent: string;
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-border bg-surface p-6 transition-colors hover:border-border-strong">
      <div
        className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: `radial-gradient(circle, ${accent}22 0%, transparent 70%)`,
        }}
      />
      <div className="flex items-center gap-2 text-muted">
        <span style={{ color: accent }}>{icon}</span>
        <p className="text-xs uppercase tracking-[0.18em]">{label}</p>
      </div>
      <p className="tabular mt-3 text-3xl font-semibold tracking-tight">
        {value}
      </p>
      <p className="mt-1 text-xs text-muted">{sublabel}</p>
    </div>
  );
}

function StatusDot({ online }: { online: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      <span
        className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${
          online ? "bg-up" : "bg-down"
        }`}
      />
      <span
        className={`relative inline-flex h-2 w-2 rounded-full ${
          online ? "bg-up" : "bg-down"
        }`}
      />
    </span>
  );
}
