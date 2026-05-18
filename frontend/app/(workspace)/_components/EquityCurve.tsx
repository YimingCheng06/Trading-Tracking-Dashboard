"use client";

import { useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CurvePoint } from "@/lib/api";
import { toNum } from "@/lib/format";

const BOX_HEIGHT = 320; // h-80
const PAD = 16; // p-4
const CHART_HEIGHT = BOX_HEIGHT - PAD * 2;

/**
 * 净值曲线 —— 累计盈亏随日期变化的面积图。暗色网格 + accent 描边渐变填充。
 *
 * 自己用 ResizeObserver 量容器宽度,给 AreaChart 显式像素尺寸 —— Recharts 3
 * 的 ResponsiveContainer 在 React 19 下会卡在 width(-1)/height(-1) 不渲染。
 */
export function EquityCurve({ points }: { points: CurvePoint[] }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth - PAD * 2);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const data = points.map((p) => ({
    date: p.on_date,
    pnl: toNum(p.cumulative_pnl) ?? 0,
  }));

  return (
    <div
      ref={boxRef}
      className="w-full rounded-2xl border border-border bg-surface/60 p-4"
      style={{ height: BOX_HEIGHT }}
    >
      {width > 0 && (
        <AreaChart
          width={width}
          height={CHART_HEIGHT}
          data={data}
          margin={{ top: 10, right: 16, bottom: 0, left: 8 }}
        >
          <defs>
            <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="#2a313c"
            strokeDasharray="3 3"
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tick={{ fill: "#8b949e", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#2a313c" }}
            minTickGap={32}
          />
          <YAxis
            tick={{ fill: "#8b949e", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(v: number) => v.toLocaleString("en-US")}
          />
          <Tooltip
            contentStyle={{
              background: "#151b23",
              border: "1px solid #2a313c",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#b1bac4" }}
            formatter={(v) => [
              Number(v).toLocaleString("en-US"),
              "Cumulative P&L",
            ]}
          />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="#58a6ff"
            strokeWidth={2}
            fill="url(#pnlFill)"
          />
        </AreaChart>
      )}
    </div>
  );
}
