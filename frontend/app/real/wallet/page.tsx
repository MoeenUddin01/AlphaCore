"use client";

import { useRealPortfolioLatest, useRealPositions } from "@/lib/hooks/useRealPortfolio";
import PageShell from "@/components/layout/PageShell";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";

export default function RealWalletPage() {
  const { data: snapshot, isLoading: snapLoading, error: snapErr } = useRealPortfolioLatest();
  const { data: positions, isLoading: posLoading } = useRealPositions();

  const loading = snapLoading || posLoading;
  const error = snapErr;

  return (
    <PageShell title="Real Wallet">
      <div className="mb-6 rounded-md border-2 border-red-600 bg-red-950/40 px-5 py-3 text-center text-sm font-bold tracking-wider text-red-400">
        ⚠  REAL — LIVE MONEY  ⚠
      </div>

      {error && (
        <p className="mb-4 text-[13px] text-red-400">
          Failed to load real account data — check API.
        </p>
      )}

      {/* KPI row */}
      <FadeIn>
        <div className="mb-6 grid grid-cols-4 gap-4">
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Total Value</p>
            {loading ? (
              <Skeleton className="mt-1 h-6 w-24 bg-zinc-800" />
            ) : (
              <p className="mt-1 text-[17px] font-semibold text-zinc-100">
                {formatCurrency(snapshot?.total_value ?? 0)}
              </p>
            )}
          </div>
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Cash</p>
            {loading ? (
              <Skeleton className="mt-1 h-6 w-20 bg-zinc-800" />
            ) : (
              <p className="mt-1 text-[17px] font-semibold text-zinc-100">
                {formatCurrency(snapshot?.cash ?? 0)}
              </p>
            )}
          </div>
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Realised P&L</p>
            {loading ? (
              <Skeleton className="mt-1 h-6 w-20 bg-zinc-800" />
            ) : (
              <p className={`mt-1 text-[17px] font-semibold ${(snapshot?.realised_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {formatCurrency(snapshot?.realised_pnl ?? 0)}
              </p>
            )}
          </div>
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Drawdown</p>
            {loading ? (
              <Skeleton className="mt-1 h-6 w-16 bg-zinc-800" />
            ) : (
              <p className="mt-1 text-[17px] font-semibold text-red-400">
                {(snapshot?.drawdown_pct ?? 0).toFixed(2)}%
              </p>
            )}
          </div>
        </div>
      </FadeIn>

      {/* Positions */}
      <FadeIn delay={0.1}>
        <div className="rounded-md border border-zinc-800 bg-zinc-900">
          <div className="border-b border-zinc-800 px-5 py-3">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">
              Holdings
            </p>
          </div>
          {loading ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full bg-zinc-800" />
              ))}
            </div>
          ) : positions && positions.length > 0 ? (
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500">
                  <th className="px-5 py-3 font-medium">Symbol</th>
                  <th className="px-5 py-3 font-medium">Qty</th>
                  <th className="px-5 py-3 font-medium">Entry</th>
                  <th className="px-5 py-3 font-medium">Current</th>
                  <th className="px-5 py-3 font-medium">Unrealised P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.symbol} className="border-b border-zinc-800/50 text-zinc-300">
                    <td className="px-5 py-3 font-medium text-zinc-100">{pos.symbol}</td>
                    <td className="px-5 py-3">{pos.quantity}</td>
                    <td className="px-5 py-3">{formatCurrency(pos.avg_entry_price)}</td>
                    <td className="px-5 py-3">{formatCurrency(pos.current_price)}</td>
                    <td className={`px-5 py-3 ${(pos.unrealised_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {formatCurrency(pos.unrealised_pnl ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-5 text-[13px] text-zinc-500">No holdings.</p>
          )}
        </div>
      </FadeIn>
    </PageShell>
  );
}
