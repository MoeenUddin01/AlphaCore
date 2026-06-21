"use client";

import { motion } from "framer-motion";
import type { TradeResponse } from "@/lib/types";
import CountUp from "@/components/motion/CountUp";
import { formatCurrency, timeAgo } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  FILLED: "text-zinc-300 bg-zinc-800",
  FAILED: "text-red-400 bg-red-500/10",
  REJECTED_LOT_SIZE: "text-amber-400 bg-amber-500/10",
};

function sideBadge(side: string) {
  if (side === "BUY") return "text-emerald-500 bg-emerald-500/10";
  return "text-red-500 bg-red-500/10";
}

export default function TradesTable({
  trades,
}: {
  trades: TradeResponse[];
}) {
  if (!trades.length) {
    return (
      <p className="text-center text-zinc-500 text-[13px] py-8">
        No trades yet.
      </p>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-6 gap-4 px-3 py-2 text-[11px] text-zinc-500 uppercase tracking-wider">
        <span>Time</span>
        <span>Side</span>
        <span>Symbol</span>
        <span>Reasoning</span>
        <span>Status</span>
        <span className="text-right">P&L</span>
      </div>
      {trades.map((t, i) => (
        <motion.div
          key={t.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.03 }}
          className="grid grid-cols-6 gap-4 items-center px-3 py-2.5 border-t border-zinc-800"
        >
          <span className="text-[11px] font-mono text-zinc-500">
            {timeAgo(t.created_at)}
          </span>

          <span
            className={`text-[12px] font-medium px-1.5 py-0.5 rounded ${sideBadge(t.side)}`}
          >
            {t.side}
          </span>

          <span className="text-[13px] font-medium text-zinc-200">
            {t.symbol}
          </span>

          <span
            className="text-[12px] text-zinc-400 truncate max-w-[200px]"
            title={t.reasoning}
          >
            {t.reasoning}
          </span>

          <span
            className={`text-[11px] px-1.5 py-0.5 rounded ${
              STATUS_STYLES[t.status] ?? "text-zinc-500 bg-zinc-800"
            }`}
          >
            {t.status}
          </span>

          <span
            className={`text-[12px] text-right ${
              t.pnl == null
                ? "text-zinc-600"
                : t.pnl >= 0
                  ? "text-emerald-500"
                  : "text-red-500"
            }`}
          >
            {t.pnl == null ? (
              "—"
            ) : (
              <CountUp value={t.pnl} format={formatCurrency} />
            )}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
