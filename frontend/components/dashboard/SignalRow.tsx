"use client";

import type { SignalResponse } from "@/lib/types";

export default function SignalRow({ signal }: { signal: SignalResponse }) {
  return (
    <div className="grid grid-cols-5 gap-4 items-center px-3 py-2.5 border-t border-zinc-800 text-[13px]">
      <span className="font-medium text-zinc-200">{signal.symbol}</span>
      <span className="text-zinc-400">{signal.sentiment_score.toFixed(2)}</span>
      <span className="text-zinc-500 capitalize">{signal.direction}</span>
      <span className="text-zinc-400">{(signal.confidence * 100).toFixed(0)}%</span>
      <span className="text-zinc-500">{signal.sentiment_label}</span>
    </div>
  );
}
