"use client";

import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

const COLORS = ["#378ADD", "#14B8A6", "#F97316", "#A1A1AA"];

export default function AllocationDonut({
  holdings,
  cash,
}: {
  holdings: { symbol: string; value: number }[];
  cash: number;
}) {
  const total = holdings.reduce((s, h) => s + h.value, 0) + cash;
  const chartData = [
    ...holdings.map((h) => ({ name: h.symbol, value: h.value })),
    { name: "Cash", value: cash },
  ];

  return (
    <div>
      <div className="h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius="65%"
              outerRadius="90%"
              dataKey="value"
              strokeWidth={0}
            >
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-1 mt-2">
        {chartData.map((entry, i) => {
          const pct = total > 0 ? ((entry.value / total) * 100).toFixed(1) : "0";
          return (
            <div key={entry.name} className="flex items-center gap-2">
              <span
                className="w-[9px] h-[9px] rounded-sm shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              <span className="text-[12px] font-medium text-zinc-300 flex-1">
                {entry.name}
              </span>
              <span className="text-[12px] text-zinc-500">{pct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
