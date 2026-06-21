"use client";

import { useEffect, useState } from "react";

export default function NextCycleCountdown({
  nextRunAt,
}: {
  nextRunAt: string;
}) {
  const [remaining, setRemaining] = useState("");

  useEffect(() => {
    function tick() {
      const diff = new Date(nextRunAt).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining("Now");
        return;
      }
      const m = Math.floor(diff / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setRemaining(`${m}m ${s}s`);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [nextRunAt]);

  return (
    <div className="text-center">
      <p className="text-[11px] text-zinc-500 uppercase tracking-wider">
        Next cycle
      </p>
      <p className="text-[20px] font-mono-nums font-medium text-zinc-200">
        {remaining || "—"}
      </p>
    </div>
  );
}
