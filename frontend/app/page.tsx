"use client";

import { usePortfolioHistory, usePortfolioMetrics, usePositions } from "@/lib/hooks/usePortfolio";
import { useLatestSignals } from "@/lib/hooks/useSignals";
import { useSentimentValidation } from "@/lib/hooks/useValidation";
import PageShell from "@/components/layout/PageShell";
import KpiCard from "@/components/dashboard/KpiCard";
import PipelineStrip from "@/components/dashboard/PipelineStrip";
import PortfolioChart from "@/components/dashboard/PortfolioChart";
import AllocationDonut from "@/components/dashboard/AllocationDonut";
import FearGreedGauge from "@/components/dashboard/FearGreedGauge";
import ValidationBanner from "@/components/dashboard/ValidationBanner";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";

const PIPELINE_STAGES = [
  { name: "Monitor Exits", icon: "monitor_exits", detail: "Check SL/TP conditions", status: "idle" as const },
  { name: "Manager", icon: "manager", detail: "Rank signals, generate trades", status: "idle" as const },
  { name: "Risk", icon: "risk", detail: "VaR, concentration, drawdown", status: "idle" as const },
  { name: "Execution", icon: "execution", detail: "Route orders to Binance", status: "idle" as const },
  { name: "Monitor Update", icon: "monitor_update", detail: "P&L, rebalance, persist", status: "idle" as const },
];

export default function OverviewPage() {
  const { data: history, isLoading: histLoading, error: histErr } = usePortfolioHistory();
  const { data: metrics, isLoading: metLoading } = usePortfolioMetrics();
  const { data: positions, isLoading: posLoading } = usePositions();
  const { data: signals, isLoading: sigLoading } = useLatestSignals();
  const { data: validation, isLoading: valLoading } = useSentimentValidation();

  const loading = histLoading || metLoading || posLoading || sigLoading || valLoading;
  const error = histErr;

  if (error) {
    return (
      <PageShell title="Overview">
        <p className="text-zinc-500 text-[13px]">
          Unable to load data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const latestSnapshot = history?.[0];
  const cash = latestSnapshot ? latestSnapshot.cash : 0;
  const totalValue = latestSnapshot?.total_value ?? 0;

  return (
    <PageShell title="Overview">
      <div className="space-y-6">
        {/* Validation banner */}
        {validation && (
          <FadeIn>
            <ValidationBanner
              current={validation.total_sentiment_trades}
              target={30}
              isReady={validation.is_statistically_ready}
            />
          </FadeIn>
        )}

        {/* KPI row */}
        <FadeIn delay={0.1}>
          <div className="grid grid-cols-4 gap-4">
            <KpiCard
              label="Portfolio value"
              value={totalValue}
              format="currency"
              loading={loading}
            />
            <KpiCard
              label="Realised P&L"
              value={metrics?.total_realised_pnl ?? 0}
              format="currency"
              delta={
                metrics ? { value: metrics.total_realised_pnl / 100, label: `${metrics.total_trades} trades` } : undefined
              }
              loading={loading}
            />
            <KpiCard
              label="Drawdown"
              value={metrics?.current_drawdown ?? 0}
              format="percent"
              loading={loading}
            />
            <KpiCard
              label="Open positions"
              value={positions?.length ?? 0}
              format="number"
              loading={loading}
            />
          </div>
        </FadeIn>

        {/* Pipeline strip */}
        <FadeIn delay={0.2}>
          <PipelineStrip stages={PIPELINE_STAGES} />
        </FadeIn>

        {/* Charts row */}
        <FadeIn delay={0.3}>
          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
              <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
                Portfolio value history
              </p>
              {loading ? (
                <Skeleton className="h-[220px] bg-zinc-800" />
              ) : (
                <PortfolioChart data={history ?? []} />
              )}
            </div>
            <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
              <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
                Allocation
              </p>
              {loading ? (
                <Skeleton className="h-[220px] bg-zinc-800" />
              ) : (
                <AllocationDonut
                  holdings={(positions ?? []).map((p: any) => ({
                    symbol: p.symbol,
                    value: parseFloat(p.value) || parseFloat(p.entry_price) * parseFloat(p.quantity) || 0,
                  }))}
                  cash={cash}
                />
              )}
            </div>
          </div>
        </FadeIn>

        {/* Bottom row */}
        <FadeIn delay={0.35}>
          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
              <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
                Fear & Greed
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
              ) : loading ? (
                <Skeleton className="h-16 bg-zinc-800" />
              ) : (
                <p className="text-zinc-500 text-[13px]">No data yet</p>
              )}
            </div>
            <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900 flex flex-col justify-center items-center">
              <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-2">
                Next cycle
              </p>
              <p className="text-[13px] text-zinc-400">Cycle runs hourly</p>
            </div>
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}
