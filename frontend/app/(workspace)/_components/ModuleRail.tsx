"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { moduleGroups, accounts } from "../_config/workspace";
import { IconSearch } from "./icons";

/**
 * Second column: the account-specific icon menu. Renders only when an
 * account is selected. Items are icon-only with hover tooltips — text
 * appears on pointer enter, matching the "只有鼠标放上去才出现文字" rule.
 */
export function ModuleRail({ activeAccountId }: { activeAccountId: string }) {
  const pathname = usePathname();
  const account = accounts.find((a) => a.id === activeAccountId) ?? accounts[0];

  return (
    <nav
      className="relative flex h-full flex-col items-center gap-2 border-r border-border/70 bg-rail py-4"
      style={{ width: "var(--module-width)" }}
    >
      <AccountBadge tint={account.tint} short={account.short} label={account.label} />
      <GroupDivider />
      <SearchButton />
      <GroupDivider />

      <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
        {moduleGroups.map((group, gi) => (
          <div key={group.id} className="flex flex-col items-center gap-1">
            {gi > 0 && <GroupDivider />}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <div key={item.id} className="rail-group rail-item relative" data-active={active} data-hover>
                  <span className="rail-indicator" />
                  <Link
                    href={item.href}
                    className="flex items-center justify-center transition-all duration-150"
                    style={{
                      width: "var(--icon-size)",
                      height: "var(--icon-size)",
                      borderRadius: active
                        ? "var(--icon-radius-active)"
                        : "var(--icon-radius)",
                      background: active
                        ? "var(--accent-soft)"
                        : "transparent",
                      color: active ? "var(--accent)" : "var(--muted-strong)",
                    }}
                    aria-label={item.label}
                  >
                    <Icon width={20} height={20} />
                  </Link>
                  <span className="rail-tooltip">
                    {item.label}
                    <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">
                      {group.label}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}

function AccountBadge({
  tint,
  short,
  label,
}: {
  tint: string;
  short: string;
  label: string;
}) {
  return (
    <div className="rail-group relative">
      <div
        className="flex items-center justify-center text-xs font-semibold"
        style={{
          width: "var(--icon-size)",
          height: "var(--icon-size)",
          borderRadius: "var(--icon-radius-active)",
          background: `${tint}22`,
          color: tint,
          border: `1px solid ${tint}55`,
        }}
      >
        {short}
      </div>
      <span className="rail-tooltip">{label}</span>
    </div>
  );
}

function SearchButton() {
  return (
    <div className="rail-group rail-item relative" data-hover>
      <span className="rail-indicator" />
      <button
        type="button"
        className="flex items-center justify-center text-muted-strong transition-colors hover:text-foreground"
        style={{
          width: "var(--icon-size)",
          height: "var(--icon-size)",
          borderRadius: "var(--icon-radius)",
          background: "var(--surface)",
        }}
        aria-label="Search"
      >
        <IconSearch width={18} height={18} />
      </button>
      <span className="rail-tooltip">
        Search
        <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">
          ⌘K
        </span>
      </span>
    </div>
  );
}

function GroupDivider() {
  return <div className="my-1 h-px w-6 bg-border/60" />;
}
