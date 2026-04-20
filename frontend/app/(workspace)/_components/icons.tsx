import type { SVGProps } from "react";

/**
 * Minimal inline SVG icon set. All icons share a 24×24 viewBox with 1.6
 * stroke, rounded joins — matches the Robinhood/TradingView visual weight.
 * Using inline SVG avoids a runtime icon dependency for Phase 0/1.
 */
type IconProps = SVGProps<SVGSVGElement>;

const base: IconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

function Svg({ children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg {...base} {...rest}>
      {children}
    </svg>
  );
}

export function IconLayout(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="3" width="18" height="18" rx="2.5" />
      <path d="M3 10h18" />
      <path d="M10 10v11" />
    </Svg>
  );
}

export function IconBriefcase(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M3 13h18" />
    </Svg>
  );
}

export function IconWallet(p: IconProps) {
  return (
    <Svg {...p}>
      <rect x="3" y="6" width="18" height="14" rx="2" />
      <path d="M16 13h3" />
      <path d="M3 10h15" />
    </Svg>
  );
}

export function IconCoins(p: IconProps) {
  return (
    <Svg {...p}>
      <ellipse cx="9" cy="7" rx="6" ry="3" />
      <path d="M3 7v5c0 1.7 2.7 3 6 3s6-1.3 6-3V7" />
      <path d="M9 13v4c0 1.7 2.7 3 6 3s6-1.3 6-3v-5" />
      <ellipse cx="15" cy="12" rx="6" ry="3" />
    </Svg>
  );
}

export function IconArrowSwap(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4 7h13" />
      <path d="m14 4 3 3-3 3" />
      <path d="M20 17H7" />
      <path d="m10 20-3-3 3-3" />
    </Svg>
  );
}

export function IconReceipt(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M5 3h14v18l-3-2-3 2-3-2-3 2-2-2V3z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h4" />
    </Svg>
  );
}

export function IconUpload(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 15V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Svg>
  );
}

export function IconTrendingUp(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="m3 17 6-6 4 4 8-8" />
      <path d="M14 7h7v7" />
    </Svg>
  );
}

export function IconSparkLine(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 20V4" />
      <path d="M3 20h18" />
      <path d="m7 15 3-4 3 3 5-7" />
    </Svg>
  );
}

export function IconPercent(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="m19 5-14 14" />
      <circle cx="7.5" cy="7.5" r="2.5" />
      <circle cx="16.5" cy="16.5" r="2.5" />
    </Svg>
  );
}

export function IconBrain(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M9 3a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 2 5v1a3 3 0 0 0 6 0V3a3 3 0 0 0-3 0Z" />
      <path d="M15 3a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-2 5v1a3 3 0 0 1-6 0" />
    </Svg>
  );
}

export function IconNewspaper(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4 4h13v16H6a2 2 0 0 1-2-2V4z" />
      <path d="M17 8h3v10a2 2 0 0 1-2 2" />
      <path d="M8 8h5" />
      <path d="M8 12h5" />
      <path d="M8 16h5" />
    </Svg>
  );
}

export function IconKey(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="8" cy="15" r="4" />
      <path d="m11 12 9-9" />
      <path d="m17 6 3 3" />
      <path d="m14 9 2 2" />
    </Svg>
  );
}

export function IconPlug(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M9 2v5" />
      <path d="M15 2v5" />
      <path d="M7 7h10v4a5 5 0 0 1-10 0V7z" />
      <path d="M12 16v6" />
    </Svg>
  );
}

export function IconSliders(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
      <circle cx="9" cy="7" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="7" cy="17" r="2" />
    </Svg>
  );
}

export function IconPlus(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </Svg>
  );
}

export function IconSearch(p: IconProps) {
  return (
    <Svg {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Svg>
  );
}
