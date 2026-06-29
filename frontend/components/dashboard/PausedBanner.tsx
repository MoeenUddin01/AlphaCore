"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import type { TradingStatusResponse } from "@/lib/types";
import { motion } from "framer-motion";
import { AlertTriangle, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

export default function PausedBanner() {
  const queryClient = useQueryClient();
  const [resuming, setResuming] = useState(false);

  const { data: status } = useQuery<TradingStatusResponse>({
    queryKey: ["trading-status"],
    queryFn: () => api.getTradingStatus(),
    refetchInterval: 30_000,
  });

  if (!status?.is_paused) return null;

  const handleResume = async () => {
    setResuming(true);
    try {
      await api.resumeTrading();
      await queryClient.invalidateQueries({ queryKey: ["trading-status"] });
    } catch {
      // silent
    }
    setResuming(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2.5 flex items-center justify-between"
    >
      <div className="flex items-center gap-2.5">
        <span className="text-amber-400 shrink-0">
          <AlertTriangle size={18} />
        </span>
        <p className="text-[13px] text-amber-200 font-medium">
          Trading paused
        </p>
        <p className="text-[12px] text-amber-400/70">
          New entry trades are not being generated. Auto-exits (SL/TP) still
          active.
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        disabled={resuming}
        onClick={handleResume}
        className="border-amber-600/40 text-amber-300 hover:bg-amber-500/10 text-[12px] h-8 gap-1.5"
      >
        <Play size={14} />
        {resuming ? "Resuming…" : "Resume trading"}
      </Button>
    </motion.div>
  );
}
