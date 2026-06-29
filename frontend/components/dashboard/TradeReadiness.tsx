"use client";

import type { SignalResponse } from "@/lib/types";
import { motion } from "framer-motion";
import { ArrowUpCircle, ArrowDownCircle, MinusCircle } from "lucide-react";

function sentimentColor(score: number): string {
  if (score > 0.3) return "bg-emerald-500";
  if (score < -0.3) return "bg-red-500";
  return "bg-zinc-600";
}

function sentimentBorder(score: number): string {
  if (score > 0.3) return "border-emerald-500/40";
  if (score < -0.3) return "border-red-500/40";
  return "border-zinc-700";
}

export default function TradeReadiness({
  signals,
}: {
  signals: SignalResponse[];
}) {
  if (!signals || signals.length === 0) return null;

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-4">
        Trade Readiness
      </p>
      <div className="space-y-3">
        {signals.map((sig) => {
          const score = sig.sentiment_score;
          const barPct = Math.min(
            Math.max((score + 1) / 2 * 100, 0),
            100,
          );
          const thresholdPct = Math.min(
            Math.max((0.3 + 1) / 2 * 100, 0),
            100,
          );
          const negThresholdPct = Math.min(
            Math.max((-0.3 + 1) / 2 * 100, 0),
            100,
          );
          const nearThreshold = sig.distance_to_threshold < 0.15;

          let actionLabel: string;
          let actionIcon: React.ReactNode;
          if (sig.has_holding) {
            if (score <= -0.3) {
              actionLabel = "Ready to SELL";
              actionIcon = <ArrowDownCircle size={14} className="text-red-400" />;
            } else if (score < 0.3) {
              actionLabel = `Would SELL at −0.30 (${sig.distance_to_threshold.toFixed(2)} away)`;
              actionIcon = <ArrowDownCircle size={14} className="text-zinc-500" />;
            } else {
              actionLabel = `Holding — SELL target is −0.30 (${sig.distance_to_threshold.toFixed(2)} away)`;
              actionIcon = <MinusCircle size={14} className="text-zinc-500" />;
            }
          } else {
            if (score >= 0.3) {
              actionLabel = "Ready to BUY";
              actionIcon = <ArrowUpCircle size={14} className="text-emerald-400" />;
            } else if (score > -0.3) {
              actionLabel = `Would BUY at +0.30 (${sig.distance_to_threshold.toFixed(2)} away)`;
              actionIcon = <ArrowUpCircle size={14} className="text-zinc-500" />;
            } else {
              actionLabel = `Not holding — BUY target is +0.30 (${sig.distance_to_threshold.toFixed(2)} away)`;
              actionIcon = <MinusCircle size={14} className="text-zinc-500" />;
            }
          }

          return (
            <motion.div
              key={sig.symbol}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={`rounded border ${sentimentBorder(score)} px-3 py-2.5 ${
                nearThreshold ? "bg-zinc-800/60" : ""
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-zinc-200 min-w-[88px]">
                    {sig.symbol.replace("/USDT", "")}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${sentimentColor(score)}`}
                    />
                    <span className="text-[12px] text-zinc-400">
                      {score > 0 ? "+" : ""}{score.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-[12px]">
                  {actionIcon}
                  <span
                    className={
                      nearThreshold
                        ? "text-amber-300 font-medium"
                        : "text-zinc-400"
                    }
                  >
                    {actionLabel}
                  </span>
                </div>
              </div>

              {/* Sentiment bar */}
              <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="absolute top-0 bottom-0 w-[1px] bg-zinc-500 z-10"
                  style={{ left: `${thresholdPct}%` }}
                />
                <div
                  className="absolute top-0 bottom-0 w-[1px] bg-zinc-500 z-10"
                  style={{ left: `${negThresholdPct}%` }}
                />
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${barPct}%` }}
                  transition={{ duration: 0.6, ease: "easeOut" }}
                  className={`h-full rounded-full ${sentimentColor(score)}`}
                  style={{ opacity: 0.7 }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-zinc-600 mt-1">
                <span>−1.0</span>
                <span>−0.30 SELL</span>
                <span>0</span>
                <span>+0.30 BUY</span>
                <span>+1.0</span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
