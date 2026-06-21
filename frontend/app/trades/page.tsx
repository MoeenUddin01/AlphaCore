"use client";

import { useState } from "react";
import { useTradeHistory, useTradeStats } from "@/lib/hooks/useTrades";
import PageShell from "@/components/layout/PageShell";
import KpiCard from "@/components/dashboard/KpiCard";
import TradesTable from "@/components/dashboard/TradesTable";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";

export default function TradesPage() {
  const [symbolFilter, setSymbolFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<
    "ALL" | "FILLED" | "FAILED" | "REJECTED_LOT_SIZE"
  >("ALL");

  const { data: trades, isLoading, error } = useTradeHistory(200, symbolFilter);
  const { data: stats } = useTradeStats();

  const filtered = statusFilter === "ALL"
    ? (trades ?? [])
    : (trades ?? []).filter((t) => t.status === statusFilter);

  if (error) {
    return (
      <PageShell title="Trade history">
        <p className="text-zinc-500 text-[13px]">
          Unable to load data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const uniqueSymbols = [...new Set((trades ?? []).map((t) => t.symbol))];

  // Most traded symbol
  const symbolCounts: Record<string, number> = {};
  for (const t of trades ?? []) {
    symbolCounts[t.symbol] = (symbolCounts[t.symbol] ?? 0) + 1;
  }
  const mostTraded = Object.entries(symbolCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";

  const winRate = stats?.win_rate ?? (() => {
    if (!trades?.length) return null;
    const winners = trades.filter((t) => (t.pnl ?? 0) > 0).length;
    return winners / trades.length;
  })();

  return (
    <PageShell title="Trade history">
      <div className="space-y-6">
        {/* Filters */}
        <FadeIn>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-[12px] text-zinc-500">Symbol</label>
              <select
                value={symbolFilter ?? ""}
                onChange={(e) => setSymbolFilter(e.target.value || undefined)}
                className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-[13px] text-zinc-200"
              >
                <option value="">All</option>
                {uniqueSymbols.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-[12px] text-zinc-500">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as any)}
                className="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-[13px] text-zinc-200"
              >
                <option value="ALL">All</option>
                <option value="FILLED">Filled</option>
                <option value="FAILED">Failed</option>
                <option value="REJECTED_LOT_SIZE">Rejected</option>
              </select>
            </div>
          </div>
        </FadeIn>

        {/* KPI row */}
        <FadeIn delay={0.1}>
          <div className="grid grid-cols-4 gap-4">
            <KpiCard
              label="Total trades"
              value={trades?.length ?? 0}
              format="number"
              loading={isLoading}
            />
            <KpiCard
              label="Win rate"
              value={winRate ?? 0}
              format="percent"
              loading={isLoading}
            />
            <KpiCard
              label="Total realised P&L"
              value={stats?.total_realised_pnl ?? trades?.reduce((s, t) => s + (t.pnl ?? 0), 0) ?? 0}
              format="currency"
              loading={isLoading}
            />
            <KpiCard
              label="Most traded"
              value={0}
              format="number"
              loading={isLoading}
            />
          </div>
        </FadeIn>

        {/* Trades table */}
        <FadeIn delay={0.2}>
          <div className="rounded-md border border-zinc-800 bg-zinc-900">
            <div className="px-3 py-2.5 border-b border-zinc-800">
              <p className="text-[13px] font-medium text-zinc-200">
                Trades {statusFilter !== "ALL" && `(${statusFilter})`}
              </p>
            </div>
            {isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-8 bg-zinc-800" />
                <Skeleton className="h-8 bg-zinc-800" />
                <Skeleton className="h-8 bg-zinc-800" />
              </div>
            ) : (
              <TradesTable trades={filtered} />
            )}
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}
