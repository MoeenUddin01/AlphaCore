"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { formatCurrency } from "@/lib/utils";

function shortTime(iso: string) {
  const d = new Date(iso);
  return `${d.getHours().toString().padStart(2, "0")}:${d
    .getMinutes()
    .toString()
    .padStart(2, "0")}`;
}

export default function PortfolioChart({
  data,
}: {
  data: { created_at: string; total_value: number }[];
}) {
  return (
    <div className="h-[220px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#378ADD" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#378ADD" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="created_at"
            tickFormatter={shortTime}
            stroke="rgba(255,255,255,0.2)"
            tick={{ fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
            stroke="rgba(255,255,255,0.2)"
            tick={{ fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #27272a",
              borderRadius: "6px",
              fontSize: 12,
            }}
            labelFormatter={(label) => shortTime(String(label))}
            formatter={(value) => [formatCurrency(Number(value)), "Value"]}
          />
          <Area
            type="monotone"
            dataKey="total_value"
            stroke="#378ADD"
            strokeWidth={2}
            fill="url(#portfolioGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
