"use client";

import { useState } from "react";
import type { Account } from "@/lib/api";
import { accountTint, accountShort } from "@/lib/accounts";
import { IconPlus } from "./icons";

/**
 * 最左 72px 栏:账户切换器。账户来自 GET /accounts,选中态由父级
 * 从 URL 解析后下传。无账户时只显示 Logo + Add。
 */
export function AccountRail({
  accounts,
  activeId,
  onSelect,
}: {
  accounts: Account[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside
      className="relative flex h-full flex-col items-center gap-3 border-r border-black/40 bg-rail-deep py-4"
      style={{ width: "var(--rail-width)" }}
    >
      <Logo />
      <Divider />
      <ul className="flex flex-col gap-3">
        {accounts.map((acct, i) => (
          <li key={acct.broker_account_id}>
            <AccountPill
              label={acct.name}
              short={accountShort(acct)}
              tint={accountTint(i)}
              active={activeId === acct.broker_account_id}
              onClick={() => onSelect(acct.broker_account_id)}
            />
          </li>
        ))}
      </ul>
      <Divider />
      <AddButton />
    </aside>
  );
}

function Logo() {
  return (
    <div
      className="flex h-10 w-10 items-center justify-center rounded-[12px] font-mono text-sm font-bold tracking-tight"
      style={{
        background:
          "linear-gradient(135deg, rgba(88,166,255,0.9), rgba(38,166,154,0.9))",
        color: "#0a0f16",
      }}
    >
      TD
    </div>
  );
}

function Divider() {
  return <div className="h-px w-8 bg-border/60" />;
}

function AccountPill({
  label,
  short,
  tint,
  active,
  onClick,
}: {
  label: string;
  short: string;
  tint: string;
  active: boolean;
  onClick: () => void;
}) {
  const [hover, setHover] = useState(false);
  const morph = active || hover;

  return (
    <div
      className="rail-group rail-item relative"
      data-active={active}
      data-hover
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="rail-indicator" />
      <button
        type="button"
        onClick={onClick}
        className="relative flex items-center justify-center font-semibold transition-all duration-200"
        style={{
          width: "var(--icon-size)",
          height: "var(--icon-size)",
          borderRadius: morph
            ? "var(--icon-radius-active)"
            : "calc(var(--icon-size) / 2)",
          background: active ? tint : "var(--surface)",
          color: active ? "#0a0f16" : "var(--muted-strong)",
          boxShadow: active ? `0 0 0 2px ${tint}44, 0 6px 18px ${tint}33` : "none",
        }}
        aria-label={label}
      >
        <span className="text-sm tracking-tight">{short}</span>
      </button>
      <span className="rail-tooltip">{label}</span>
    </div>
  );
}

function AddButton() {
  return (
    <div className="rail-group relative">
      <button
        type="button"
        className="flex items-center justify-center rounded-full border border-dashed border-border text-muted transition-colors hover:border-up hover:text-up"
        style={{
          width: "var(--icon-size)",
          height: "var(--icon-size)",
        }}
        aria-label="Add account"
      >
        <IconPlus width={18} height={18} />
      </button>
      <span className="rail-tooltip">Add account</span>
    </div>
  );
}
