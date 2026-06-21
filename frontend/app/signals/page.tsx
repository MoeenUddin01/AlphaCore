"use client";

import { useLatestSignals, useSignalsSummary } from "@/lib/hooks/useSignals";
import PageShell from "@/components/layout/PageShell";
import KpiCard from "@/components/dashboard/KpiCard";
import SignalsTable from "@/components/dashboard/SignalsTable";
import FearGreedGauge from "@/components/dashboard/FearGreedGauge";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";

export default function SignalsPage() {
  const { data: signals, isLoading, error } = useLatestSignals();
  const { data: summary } = useSignalsSummary();

  if (error) {
    return (
      <PageShell title="ML signals">
        <p className="text-zinc-500 text-[13px]">
          Unable to load data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const bullish = summary?.bullish ?? signals?.filter((s) => s.sentiment_score > 0.3).length ?? 0;
  const bearish = summary?.bearish ?? signals?.filter((s) => s.sentiment_score < -0.3).length ?? 0;
  const neutral = summary?.neutral ?? signals?.filter((s) => Math.abs(s.sentiment_score) <= 0.3).length ?? 0;

  return (
    <PageShell title="ML signals">
      <div className="space-y-6">
        {/* KPI row */}
        <FadeIn>
          <div className="grid grid-cols-3 gap-4">
            <KpiCard label="Bullish" value={bullish} format="number" loading={isLoading} />
            <KpiCard label="Bearish" value={bearish} format="number" loading={isLoading} />
            <KpiCard label="Neutral" value={neutral} format="number" loading={isLoading} />
          </div>
        </FadeIn>

        {/* Signals table */}
        <FadeIn delay={0.1}>
          <div className="rounded-md border border-zinc-800 bg-zinc-900">
            <div className="px-3 py-2.5 border-b border-zinc-800">
              <p className="text-[13px] font-medium text-zinc-200">
                Latest signals
              </p>
            </div>
            {isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-8 bg-zinc-800" />
                <Skeleton className="h-8 bg-zinc-800" />
                <Skeleton className="h-8 bg-zinc-800" />
              </div>
            ) : (
              <SignalsTable signals={signals ?? []} />
            )}
          </div>
        </FadeIn>

        {/* Fear & Greed */}
        <FadeIn delay={0.2}>
          <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
              Market sentiment
            </p>
            {signals && signals.length > 0 ? (
              <FearGreedGauge
                value={signals[0].fear_greed_value}
                classification={
                  signals[0].fear_greed_value <= 25
                    ? "Extreme Fear"
                    : signals[0].fear_greed_value <= 45
                      ? "Fear"
                      : signals[0].fear_greed_value <= 55
                        ? "Neutral"
                        : signals[0].fear_greed_value <= 75
                          ? "Greed"
                          : "Extreme Greed"
                }
              />
            ) : isLoading ? (
              <Skeleton className="h-16 bg-zinc-800" />
            ) : (
              <p className="text-zinc-500 text-[13px]">No data yet</p>
            )}
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}
