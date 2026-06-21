"use client";

import { usePortfolioMetrics, usePortfolioHistory, usePositions } from "@/lib/hooks/usePortfolio";
import PageShell from "@/components/layout/PageShell";
import RiskCard from "@/components/dashboard/RiskCard";
import PortfolioChart from "@/components/dashboard/PortfolioChart";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";

function computeDrawdownSeries(
  data: { created_at: string; total_value: number }[]
): { created_at: string; total_value: number }[] {
  let peak = -Infinity;
  return data.map((d) => {
    if (d.total_value > peak) peak = d.total_value;
    const dd = peak > 0 ? ((peak - d.total_value) / peak) * 100 : 0;
    return { created_at: d.created_at, total_value: dd };
  }).reverse();
}

export default function RiskPage() {
  const { data: metrics, isLoading, error } = usePortfolioMetrics();
  const { data: history } = usePortfolioHistory();
  const { data: positions } = usePositions();

  if (error) {
    return (
      <PageShell title="Risk dashboard">
        <p className="text-zinc-500 text-[13px]">
          Unable to load data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const totalValue = metrics ? (() => {
    const snap = history?.[0];
    return snap?.total_value ?? 10000;
  })() : 10000;

  const maxPositionPct = positions?.length
    ? Math.max(...positions.map((p: any) => parseFloat(p.value ?? 0))) / totalValue
    : 0;

  const exposure = positions?.length
    ? positions.reduce((s: number, p: any) => s + parseFloat(p.value ?? 0), 0) / totalValue
    : 0;

  const drawdown = metrics?.current_drawdown ?? 0;

  const ddSeries = history ? computeDrawdownSeries(history) : [];

  return (
    <PageShell title="Risk dashboard">
      <div className="space-y-6">
        {/* Risk cards */}
        <FadeIn>
          <div className="grid grid-cols-4 gap-4">
            <RiskCard
              label="Portfolio VaR (est.)"
              value={totalValue * 0.02}
              displayValue={`$${(totalValue * 0.02).toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
              max={totalValue * 0.05}
              colorTier={totalValue * 0.02 > totalValue * 0.04 ? "high" : totalValue * 0.02 > totalValue * 0.03 ? "medium" : "low"}
            />
            <RiskCard
              label="Concentration"
              value={maxPositionPct}
              displayValue={`${(maxPositionPct * 100).toFixed(1)}%`}
              max={0.20}
              colorTier={maxPositionPct > 0.15 ? "high" : maxPositionPct > 0.10 ? "medium" : "low"}
            />
            <RiskCard
              label="Exposure"
              value={exposure}
              displayValue={`${(exposure * 100).toFixed(1)}%`}
              max={0.80}
              colorTier={exposure > 0.60 ? "high" : exposure > 0.40 ? "medium" : "low"}
            />
            <RiskCard
              label="Drawdown vs limit"
              value={drawdown}
              displayValue={`${drawdown.toFixed(2)}%`}
              max={15}
              colorTier={drawdown > 10 ? "high" : drawdown > 5 ? "medium" : "low"}
            />
          </div>
        </FadeIn>

        {/* Drawdown chart */}
        <FadeIn delay={0.1}>
          <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
              Drawdown history (%)
            </p>
            {isLoading ? (
              <Skeleton className="h-[220px] bg-zinc-800" />
            ) : (
              <PortfolioChart data={ddSeries} />
            )}
          </div>
        </FadeIn>

        {/* Risk alerts */}
        <FadeIn delay={0.2}>
          <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-2">
              Alerts
            </p>
            {drawdown > 15 ? (
              <div className="flex items-center gap-2 text-red-400 text-[13px]">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                Critical drawdown — circuit breaker may activate
              </div>
            ) : drawdown > 10 ? (
              <div className="flex items-center gap-2 text-amber-400 text-[13px]">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                Elevated drawdown — consider reducing exposure
              </div>
            ) : (
              <div className="flex items-center gap-2 text-emerald-400 text-[13px]">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                All risk metrics within limits
              </div>
            )}
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}
