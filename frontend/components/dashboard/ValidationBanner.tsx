"use client";

import { motion } from "framer-motion";
import { TestTube2, CheckCircle2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";

export default function ValidationBanner({
  current,
  target = 30,
  isReady,
}: {
  current: number;
  target?: number;
  isReady: boolean;
}) {
  const pct = Math.min((current / target) * 100, 100);

  return (
    <motion.div
      animate={{
        backgroundColor: isReady
          ? "rgba(16,185,129,0.1)"
          : "rgba(245,158,11,0.1)",
      }}
      className="rounded-md border px-4 py-3 flex items-center gap-4"
      style={{
        borderColor: isReady
          ? "rgba(16,185,129,0.3)"
          : "rgba(245,158,11,0.3)",
      }}
    >
      <div className="flex items-center gap-2 flex-1">
        {isReady ? (
          <span className="text-emerald-500 shrink-0"><CheckCircle2 size={20} /></span>
        ) : (
          <span className="text-amber-500 shrink-0"><TestTube2 size={20} /></span>
        )}
        <div>
          <p className="text-[13px] font-medium text-zinc-200">
            {isReady
              ? "Validation sample complete"
              : "Strategy validation in progress"}
          </p>
          <p className="text-[11px] text-zinc-500">
            {isReady
              ? "Sentiment strategy has enough trade data for statistical analysis."
              : `${target} trades needed before sentiment validation becomes statistically meaningful.`}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 min-w-[160px]">
        <Progress value={pct} className="h-2" />
        <span className="text-[11px] text-zinc-400 whitespace-nowrap">
          {current} / {target} trades
        </span>
      </div>
    </motion.div>
  );
}
