"use client";

import { motion } from "framer-motion";
import type { SignalResponse } from "@/lib/types";

function sentimentColor(score: number): string {
  if (score > 0) return "bg-emerald-500";
  if (score < 0) return "bg-red-500";
  return "bg-zinc-600";
}

function actionBadge(score: number) {
  if (score > 0.3) return { label: "BUY", cls: "text-emerald-500 bg-emerald-500/10" };
  if (score < -0.3) return { label: "SELL", cls: "text-red-500 bg-red-500/10" };
  return { label: "SKIP", cls: "text-zinc-500 bg-zinc-800" };
}

export default function SignalsTable({
  signals,
}: {
  signals: SignalResponse[];
}) {
  if (!signals.length) {
    return (
      <p className="text-center text-zinc-500 text-[13px] py-8">
        No signals yet this cycle.
      </p>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-5 gap-4 px-3 py-2 text-[11px] text-zinc-500 uppercase tracking-wider">
        <span>Symbol</span>
        <span>Sentiment</span>
        <span>Vol regime</span>
        <span className="text-right">Confidence</span>
        <span className="text-right">Action</span>
      </div>
      {signals.map((s, i) => {
        const action = actionBadge(s.sentiment_score);
        return (
          <motion.div
            key={s.symbol}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.05 }}
            className="grid grid-cols-5 gap-4 items-center px-3 py-2.5 border-t border-zinc-800"
          >
            <span className="text-[13px] font-medium text-zinc-200">
              {s.symbol}
            </span>

            {/* Sentiment bar */}
            <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden w-24">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-px h-full bg-zinc-600" />
              </div>
              <div
                className={`h-full rounded-full ${sentimentColor(s.sentiment_score)}`}
                style={{
                  width: `${Math.min(Math.abs(s.sentiment_score) * 50, 50)}%`,
                  marginLeft: s.sentiment_score >= 0 ? "50%" : undefined,
                  marginRight: s.sentiment_score < 0 ? "50%" : undefined,
                  float: s.sentiment_score >= 0 ? "right" : "left",
                }}
              />
            </div>

            {/* Vol regime */}
            <span
              className={`text-[12px] px-1.5 py-0.5 rounded ${
                s.confidence > 0.6
                  ? "text-amber-500 bg-amber-500/10"
                  : "text-emerald-500 bg-emerald-500/10"
              }`}
            >
              {s.confidence > 0.6 ? "HIGH" : "LOW"}
            </span>

            <span className="text-[12px] text-zinc-400 text-right">
              {(s.confidence * 100).toFixed(1)}%
            </span>

            <span
              className={`text-[12px] font-medium text-right px-2 py-0.5 rounded ${action.cls}`}
            >
              {action.label}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}
