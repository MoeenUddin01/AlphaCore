"use client";

import { useEffect, useState } from "react";
import { useSpring, useMotionValueEvent } from "framer-motion";

export default function CountUp({
  value,
  format,
  duration = 0.6,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [displayValue, setDisplayValue] = useState(
    format ? format(value) : value.toFixed(2)
  );
  const spring = useSpring(0, {
    stiffness: 80,
    damping: 20,
    mass: 0.5,
  });

  useMotionValueEvent(spring, "change", (v) => {
    setDisplayValue(format ? format(v) : v.toFixed(2));
  });

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <span className="font-mono-nums">{displayValue}</span>;
}
