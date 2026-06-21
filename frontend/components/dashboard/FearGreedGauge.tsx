"use client";

import { motion } from "framer-motion";
import CountUp from "@/components/motion/CountUp";

function valueColor(v: number): string {
  if (v <= 25) return "text-red-500";
  if (v <= 45) return "text-amber-500";
  if (v <= 55) return "text-zinc-400";
  if (v <= 75) return "text-lime-400";
  return "text-emerald-400";
}

function interpretLabel(label: string): string {
  switch (label?.toLowerCase()) {
    case "extreme fear":
      return "Market is panicking";
    case "fear":
      return "Market is cautious";
    case "neutral":
      return "Market is balanced";
    case "greed":
      return "Market is optimistic";
    case "extreme greed":
      return "Market is euphoric";
    default:
      return "Market sentiment unclear";
  }
}

export default function FearGreedGauge({
  value,
  classification,
}: {
  value: number;
  classification: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className={`text-[32px] font-medium ${valueColor(value)}`}>
          <CountUp value={value} format={(n) => Math.round(n).toString()} />
        </span>

        <div className="flex-1 relative h-3 rounded-full overflow-hidden bg-zinc-800">
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                "linear-gradient(to right, #ef4444, #f59e0b, #a1a1aa, #84cc16, #10b981)",
            }}
          />
          <motion.div
            className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg"
            animate={{ left: `${value}%` }}
            transition={{ type: "spring", stiffness: 80, damping: 15 }}
          />
        </div>
      </div>

      <p className="text-[12px] text-zinc-500 capitalize">{classification}</p>
      <p className="text-[11px] text-zinc-600">{interpretLabel(classification)}</p>
    </div>
  );
}
