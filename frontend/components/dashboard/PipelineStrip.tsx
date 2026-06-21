"use client";

import { motion } from "framer-motion";
import {
  Eye,
  Brain,
  ShieldCheck,
  Zap,
  ClipboardCheck,
} from "lucide-react";
import PulseDot from "@/components/motion/PulseDot";

const ICON_MAP: Record<string, React.ComponentType<{ size?: number }>> = {
  monitor_exits: Eye,
  manager: Brain,
  risk: ShieldCheck,
  execution: Zap,
  monitor_update: ClipboardCheck,
};

export default function PipelineStrip({
  stages,
}: {
  stages: {
    name: string;
    icon: string;
    detail: string;
    status: "active" | "idle" | "warning";
  }[];
}) {
  return (
    <div
      className="grid rounded-md border border-zinc-800 overflow-hidden bg-zinc-900"
      style={{ gridTemplateColumns: `repeat(${stages.length}, 1fr)` }}
    >
      {stages.map((stage, i) => {
        const Icon = ICON_MAP[stage.icon];
        return (
          <motion.div
            key={stage.name}
            whileHover={{ backgroundColor: "rgba(255,255,255,0.03)" }}
            className="flex flex-col gap-1 p-3 border-r border-zinc-800 last:border-r-0"
          >
            <div className="flex items-center gap-2">
              {Icon && <span className="text-zinc-400"><Icon size={16} /></span>}
              <span className="text-[13px] font-medium text-zinc-300">
                {stage.name}
              </span>
              {stage.status === "active" ? (
                <PulseDot color="success" />
              ) : (
                <span className="w-[7px] h-[7px] rounded-full bg-zinc-700" />
              )}
            </div>
            <p className="text-[11px] text-zinc-500">{stage.detail}</p>
          </motion.div>
        );
      })}
    </div>
  );
}
