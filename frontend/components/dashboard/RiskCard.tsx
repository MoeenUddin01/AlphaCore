"use client";

import { motion } from "framer-motion";

const TIER_COLORS = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-red-500",
};

export default function RiskCard({
  label,
  value,
  displayValue,
  max,
  colorTier,
}: {
  label: string;
  value: number;
  displayValue: string;
  max: number;
  colorTier: "low" | "medium" | "high";
}) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;

  return (
    <div className="rounded-md p-4 bg-zinc-900 border border-zinc-800">
      <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-1">
        {label}
      </p>
      <p className="text-[22px] font-medium text-zinc-100">{displayValue}</p>
      <div className="mt-2 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${TIER_COLORS[colorTier]}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
