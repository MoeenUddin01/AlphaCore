"use client";

import type { TradeResponse } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

export default function TradeRow({ trade }: { trade: TradeResponse }) {
  return (
    <div className="grid grid-cols-6 gap-4 items-center px-3 py-2.5 border-t border-zinc-800 text-[13px]">
      <span className="text-[11px] font-mono text-zinc-500">
        {timeAgo(trade.created_at)}
      </span>
      <span
        className={`text-[12px] font-medium ${
          trade.side === "BUY" ? "text-emerald-500" : "text-red-500"
        }`}
      >
        {trade.side}
      </span>
      <span className="font-medium text-zinc-200">{trade.symbol}</span>
      <span className="text-zinc-400 truncate" title={trade.reasoning}>
        {trade.reasoning}
      </span>
      <span className="text-zinc-500 text-[11px]">{trade.status}</span>
      <span className="text-right text-zinc-400">
        {trade.pnl != null ? `$${trade.pnl.toFixed(2)}` : "—"}
      </span>
    </div>
  );
}
