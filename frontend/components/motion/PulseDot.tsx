"use client";

import { motion } from "framer-motion";

const COLORS = {
  success: "bg-[hsl(var(--ac-success))]",
  danger: "bg-[hsl(var(--ac-danger))]",
  warning: "bg-[hsl(var(--ac-warning))]",
  info: "bg-[hsl(var(--ac-info))]",
};

export default function PulseDot({
  color = "success",
}: {
  color?: "success" | "danger" | "warning" | "info";
}) {
  return (
    <motion.div
      className={`w-[7px] h-[7px] rounded-full ${COLORS[color]}`}
      animate={{ opacity: [1, 0.4, 1] }}
      transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}
