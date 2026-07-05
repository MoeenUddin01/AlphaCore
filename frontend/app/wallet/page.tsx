"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWallet } from "@/lib/hooks/usePortfolio";
import api from "@/lib/api";
import PageShell from "@/components/layout/PageShell";
import FadeIn from "@/components/motion/FadeIn";
import CountUp from "@/components/motion/CountUp";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, timeAgo } from "@/lib/utils";

export default function WalletPage() {
  const { data: wallet, isLoading, error } = useWallet();
  const queryClient = useQueryClient();
  const [selling, setSelling] = useState<string | null>(null);
  const [sellResult, setSellResult] = useState<{ symbol: string; pnl: number | null; price: number } | null>(null);

  const handleSell = async (symbol: string, quantity: number) => {
    if (!confirm(`Sell ALL ${symbol}? This will place a market order on Binance Testnet.`)) return;
    setSelling(symbol);
    setSellResult(null);
    try {
      const result = await api.sellPosition(symbol, quantity);
      setSellResult({ symbol, pnl: result.pnl, price: result.fill_price });
      queryClient.invalidateQueries({ queryKey: ["wallet"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    } catch (e: any) {
      alert(`Sell failed: ${e.message}`);
    } finally {
      setSelling(null);
    }
  };

  if (error) {
    return (
      <PageShell title="Wallet">
        <p className="text-zinc-500 text-[13px]">
          Unable to load wallet data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const holdings = wallet?.holdings ?? [];
  const closed = wallet?.closed_positions ?? [];

  const closedExclArtifacts = closed.filter((c) => !c.is_pre_fix_artifact);
  const totalRealisedExcl = closedExclArtifacts.reduce((s, c) => s + c.realized_pnl, 0);

  return (
    <PageShell title="Wallet">
      <div className="space-y-6 max-w-[960px]">
        {/* Cash balance — prominent KPI */}
        <FadeIn>
          <div className="rounded-md p-6 bg-zinc-900 border border-zinc-800">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-1">
              Cash balance
            </p>
            {isLoading ? (
              <Skeleton className="h-10 w-48 bg-zinc-800" />
            ) : (
              <p className="text-[32px] font-medium text-zinc-100">
                <CountUp value={wallet!.cash_balance} format={formatCurrency} />
              </p>
            )}
          </div>
        </FadeIn>

        {/* Holdings section */}
        <FadeIn delay={0.1}>
          <div className="rounded-md border border-zinc-800 bg-zinc-900">
            <div className="px-4 py-3 border-b border-zinc-800">
              <p className="text-[13px] font-medium text-zinc-200">
                Holdings ({holdings.length})
              </p>
            </div>

            {sellResult && (
              <div className="mx-4 mt-3 rounded border border-emerald-800 bg-emerald-950/50 px-4 py-3 text-[13px]">
                <span className="text-emerald-400 font-medium">Sold {sellResult.symbol}</span>
                <span className="text-zinc-400"> @ </span>
                <CountUp value={sellResult.price} format={formatCurrency} />
                {sellResult.pnl !== null && (
                  <span className={sellResult.pnl >= 0 ? "text-emerald-400 ml-2" : "text-red-400 ml-2"}>
                    {sellResult.pnl >= 0 ? "+" : ""}
                    <CountUp value={sellResult.pnl} format={formatCurrency} />
                  </span>
                )}
              </div>
            )}

            {isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-10 bg-zinc-800" />
              </div>
            ) : holdings.length === 0 ? (
              <p className="text-[13px] text-zinc-500 p-4">No open positions.</p>
            ) : (
              <>
                {/* Header row */}
                <div className="grid grid-cols-7 gap-2 px-4 py-2 text-[11px] uppercase text-zinc-500 tracking-wider border-b border-zinc-800">
                  <span>Coin</span>
                  <span>Qty</span>
                  <span>Entry</span>
                  <span>Now</span>
                  <span>Cost</span>
                  <span>PnL</span>
                  <span></span>
                </div>
                <div className="divide-y divide-zinc-800">
                  {holdings.map((h) => (
                    <div key={h.symbol} className="grid grid-cols-7 gap-2 px-4 py-3 text-[13px] items-center">
                      <span className="font-medium text-zinc-200">{h.symbol}</span>
                      <span className="text-zinc-400">
                        <CountUp value={h.quantity} format={(n) => n.toFixed(4)} />
                      </span>
                      <span className="text-zinc-400">
                        <CountUp value={h.avg_entry_price} format={formatCurrency} />
                      </span>
                      <span className="text-zinc-400">
                        <CountUp value={h.current_price} format={formatCurrency} />
                      </span>
                      <span className="text-zinc-400">
                        <CountUp value={h.quantity * h.avg_entry_price} format={formatCurrency} />
                      </span>
                      <span className={h.unrealized_pnl >= 0 ? "text-emerald-500 font-medium" : "text-red-500 font-medium"}>
                        {h.unrealized_pnl >= 0 ? "+" : ""}
                        <CountUp value={h.unrealized_pnl} format={formatCurrency} />
                      </span>
                      <button
                        onClick={() => handleSell(h.symbol, h.quantity)}
                        disabled={selling === h.symbol}
                        className="px-3 py-1.5 text-[12px] font-medium rounded bg-red-600/20 text-red-400 border border-red-600/30 hover:bg-red-600/40 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {selling === h.symbol ? "Selling..." : "SELL"}
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </FadeIn>

        {/* Closed positions section */}
        <FadeIn delay={0.2}>
          <div className="rounded-md border border-zinc-800 bg-zinc-900">
            <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
              <p className="text-[13px] font-medium text-zinc-200">
                Closed positions ({closedExclArtifacts.length})
              </p>
              {closed.length > 0 && (
                <span className={`text-[13px] font-medium ${
                  totalRealisedExcl >= 0 ? "text-emerald-500" : "text-red-500"
                }`}>
                  Realised P&L: <CountUp value={totalRealisedExcl} format={formatCurrency} />
                </span>
              )}
            </div>
            {isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-10 bg-zinc-800" />
                <Skeleton className="h-10 bg-zinc-800" />
              </div>
            ) : closed.length === 0 ? (
              <p className="text-[13px] text-zinc-500 p-4">No closed trades yet.</p>
            ) : (
              <div className="divide-y divide-zinc-800">
                {/* Header row */}
                <div className="grid grid-cols-8 gap-2 px-4 py-2 text-[11px] uppercase text-zinc-500 tracking-wider">
                  <span>Symbol</span>
                  <span>Buy price</span>
                  <span>Sell price</span>
                  <span>Qty</span>
                  <span>Realised P&L</span>
                  <span>P&L %</span>
                  <span>Opened</span>
                  <span>Closed</span>
                </div>
                {closed.map((c, i) => (
                  <div key={i} className="grid grid-cols-8 gap-2 px-4 py-2.5 text-[13px] items-center">
                    <span className="font-medium text-zinc-200 flex items-center gap-1.5">
                      {c.symbol}
                      {c.is_pre_fix_artifact && (
                        <Badge variant="outline" className="text-[10px] px-1 py-0 text-zinc-500 border-zinc-700">
                          pre-fix data
                        </Badge>
                      )}
                    </span>
                    <span className="text-zinc-400">
                      <CountUp value={c.buy_price} format={formatCurrency} />
                    </span>
                    <span className="text-zinc-400">
                      <CountUp value={c.sell_price} format={formatCurrency} />
                    </span>
                    <span className="text-zinc-400">
                      <CountUp value={c.quantity} format={(n) => n.toFixed(4)} />
                    </span>
                    <span className={c.realized_pnl >= 0 ? "text-emerald-500" : "text-red-500"}>
                      <CountUp value={c.realized_pnl} format={formatCurrency} />
                    </span>
                    <span className={c.realized_pnl_pct >= 0 ? "text-emerald-500" : "text-red-500"}>
                      {c.realized_pnl_pct >= 0 ? "+" : ""}
                      <CountUp value={c.realized_pnl_pct} format={(n) => n.toFixed(2) + "%"} />
                    </span>
                    <span className="text-zinc-500 text-[12px]">{timeAgo(c.opened_at)}</span>
                    <span className="text-zinc-500 text-[12px]">{timeAgo(c.closed_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}

