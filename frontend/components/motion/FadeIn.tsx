"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

export default function FadeIn({
  children,
  delay,
}: {
  children: ReactNode;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
    >
      {children}
    </motion.div>
  );
}
