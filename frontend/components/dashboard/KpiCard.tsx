"use client";

import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import CountUp from "@/components/motion/CountUp";
import { formatCurrency, formatPercent, formatCompactNumber } from "@/lib/utils";

const FORMATTERS = {
  currency: formatCurrency,
  percent: (n: number) => formatPercent(n, 2),
  number: formatCompactNumber,
};

export default function KpiCard({
  label,
  value,
  format = "number",
  delta,
  loading,
}: {
  label: string;
  value: number;
  format?: "currency" | "percent" | "number";
  delta?: { value: number; label: string };
  loading?: boolean;
}) {
  const fmt = FORMATTERS[format];

  return (
    <div className="rounded-md p-4 bg-zinc-900 border border-zinc-800">
      <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-1">
        {label}
      </p>
      {loading ? (
        <Skeleton className="h-7 w-28 bg-zinc-800" />
      ) : (
        <p className="text-[22px] font-medium text-zinc-100">
          <CountUp value={value} format={fmt} />
        </p>
      )}
      {delta && (
        <div className="flex items-center gap-1 mt-1.5">
          {delta.value >= 0 ? (
            <span className="text-emerald-500"><ArrowUpRight size={14} /></span>
          ) : (
            <span className="text-red-500"><ArrowDownRight size={14} /></span>
          )}
          <span
            className={`text-[12px] ${
              delta.value >= 0 ? "text-emerald-500" : "text-red-500"
            }`}
          >
            {formatPercent(delta.value, 2)}
          </span>
          <span className="text-[12px] text-zinc-500">{delta.label}</span>
        </div>
      )}
    </div>
  );
}
