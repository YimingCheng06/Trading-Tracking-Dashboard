"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { moduleGroups } from "../_config/workspace";
import { accountTint, accountShort } from "@/lib/accounts";
import type { Account } from "@/lib/api";
import { IconSearch } from "./icons";

/**
 * 第二栏:账户级图标菜单。账户徽标取自真实账户;导航链接保留当前
 * `?account=` query,激活态只比对 pathname(不含 query)。
 */
export function ModuleRail({
  activeAccountId,
  accounts,
}: {
  activeAccountId: string;
  accounts: Account[];
}) {
  const pathname = usePathname();
  const idx = accounts.findIndex(
    (a) => a.broker_account_id === activeAccountId,
  );
  const account = idx >= 0 ? accounts[idx] : null;

  return (
    <nav
      className="relative flex h-full flex-col items-center gap-2 border-r border-border/70 bg-rail py-4"
      style={{ width: "var(--module-width)" }}
    >
      {account && (
        <>
          <AccountBadge
            tint={accountTint(idx)}
            short={accountShort(account)}
            label={account.name}
          />
          <GroupDivider />
        </>
      )}
      <SearchButton />
      <GroupDivider />

      <div className="no-scrollbar flex flex-1 flex-col gap-1 overflow-y-auto">
        {moduleGroups.map((group, gi) => (
          <div key={group.id} className="flex flex-col items-center gap-1">
            {gi > 0 && <GroupDivider />}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              const href = activeAccountId
                ? `${item.href}?account=${encodeURIComponent(activeAccountId)}`
                : item.href;
              return (
                <div
                  key={item.id}
                  className="rail-group rail-item relative"
                  data-active={active}
                  data-hover
                >
                  <span className="rail-indicator" />
                  <Link
                    href={href}
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
