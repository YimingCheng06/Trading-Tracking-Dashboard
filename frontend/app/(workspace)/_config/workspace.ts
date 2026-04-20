import type { ComponentType, SVGProps } from "react";
import {
  IconBriefcase,
  IconLayout,
  IconWallet,
  IconCoins,
  IconArrowSwap,
  IconReceipt,
  IconUpload,
  IconTrendingUp,
  IconSparkLine,
  IconPercent,
  IconBrain,
  IconNewspaper,
  IconKey,
  IconPlug,
  IconSliders,
} from "../_components/icons";

export type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export type WorkspaceAccount = {
  id: string;
  label: string;
  short: string;
  tint: string;
  broker: string;
};

export type ModuleGroup = {
  id: string;
  label: string;
  items: ModuleItem[];
};

export type ModuleItem = {
  id: string;
  label: string;
  href: string;
  icon: IconComponent;
};

/**
 * Accounts populate the leftmost rail. `tint` drives the active-state glow
 * so each account gets a subtle identity.
 */
export const accounts: WorkspaceAccount[] = [
  {
    id: "ibkr-main",
    label: "IBKR Main",
    short: "IM",
    tint: "#58a6ff",
    broker: "Interactive Brokers Pro",
  },
  {
    id: "ibkr-paper",
    label: "IBKR Paper",
    short: "IP",
    tint: "#26a69a",
    broker: "Interactive Brokers Paper",
  },
  {
    id: "aggregate",
    label: "Aggregate",
    short: "∑",
    tint: "#c792ea",
    broker: "All accounts combined",
  },
];

/**
 * Modules populate the inner rail. Flat list with group dividers — keeps
 * the icon strip scannable without collapsible headers.
 */
export const moduleGroups: ModuleGroup[] = [
  {
    id: "portfolio",
    label: "Portfolio",
    items: [
      { id: "dashboard", label: "Dashboard", href: "/dashboard", icon: IconLayout },
      { id: "positions", label: "Positions", href: "/positions", icon: IconBriefcase },
      { id: "holdings", label: "Holdings", href: "/holdings", icon: IconWallet },
    ],
  },
  {
    id: "activity",
    label: "Activity",
    items: [
      { id: "trades", label: "Trades", href: "/trades", icon: IconArrowSwap },
      { id: "orders", label: "Orders", href: "/orders", icon: IconReceipt },
      { id: "upload", label: "Upload Statements", href: "/upload", icon: IconUpload },
    ],
  },
  {
    id: "analysis",
    label: "Analysis",
    items: [
      { id: "pnl", label: "P&L", href: "/pnl", icon: IconTrendingUp },
      { id: "performance", label: "Performance", href: "/performance", icon: IconSparkLine },
      { id: "tax", label: "Tax", href: "/tax", icon: IconPercent },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { id: "ai", label: "AI Chat", href: "/ai", icon: IconBrain },
      { id: "news", label: "News Feed", href: "/news", icon: IconNewspaper },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    items: [
      { id: "keys", label: "API Keys", href: "/settings/keys", icon: IconKey },
      { id: "providers", label: "Providers", href: "/settings/providers", icon: IconPlug },
      { id: "preferences", label: "Preferences", href: "/settings/preferences", icon: IconSliders },
    ],
  },
];

export const coinIcon = IconCoins; // exported so tests / future use can reference
