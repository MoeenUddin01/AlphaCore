"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { motion } from "framer-motion";
import api from "@/lib/api";
import { timeAgo } from "@/lib/utils";

export default function TopBar({ title }: { title: string }) {
  const [paused, setPaused] = useState(false);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 30000,
  });

  const connected = health?.database === true;

  const handleTogglePause = async () => {
    try {
      if (paused) {
        await api.resumeTrading();
      } else {
        await api.pauseTrading();
      }
      setPaused(!paused);
    } catch {
      // ignore toggle errors
    }
  };

  return (
    <header className="flex items-center justify-between h-14 px-6 border-b border-zinc-800 bg-zinc-950">
      <h1 className="text-[18px] font-medium text-zinc-100">{title}</h1>

      <div className="flex items-center gap-3">
        {/* Health indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-red-500"
            }`}
          />
          <span className="text-[12px] text-zinc-400">
            {connected ? "API connected" : "API unreachable"}
          </span>
        </div>

        {/* Last updated */}
        {health?.timestamp && (
          <span className="text-[12px] text-zinc-500">
            {timeAgo(health.timestamp)}
          </span>
        )}

        {/* Pause / Resume toggle */}
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={handleTogglePause}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
          <span>{paused ? "Resume trading" : "Pause trading"}</span>
        </motion.button>
      </div>
    </header>
  );
}
