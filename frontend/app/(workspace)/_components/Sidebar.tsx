"use client";

import { useState } from "react";
import { AccountRail } from "./AccountRail";
import { ModuleRail } from "./ModuleRail";
import { accounts } from "../_config/workspace";

/**
 * Orchestrates the two-rail Discord-style shell. Holds the active-account
 * state locally for Phase 0 (pre-multi-account data). When real accounts
 * land, lift this into a route param or URL state.
 */
export function Sidebar() {
  const [activeAccountId, setActiveAccountId] = useState<string>(accounts[0].id);

  return (
    <div className="flex h-full flex-none">
      <AccountRail activeId={activeAccountId} onSelect={setActiveAccountId} />
      <ModuleRail activeAccountId={activeAccountId} />
    </div>
  );
}
