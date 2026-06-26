"use client";

import { useSentimentValidation } from "@/lib/hooks/useValidation";
import PageShell from "@/components/layout/PageShell";
import KpiCard from "@/components/dashboard/KpiCard";
import ValidationBanner from "@/components/dashboard/ValidationBanner";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

export default function ValidationPage() {
  const { data, isLoading, error } = useSentimentValidation();

  if (error) {
    return (
      <PageShell title="Strategy validation">
        <p className="text-zinc-500 text-[13px]">
          Unable to load data — check that the API server is running.
        </p>
      </PageShell>
    );
  }

  const winRate = data?.win_rate_pct ?? 0;
  const showColor = data?.is_statistically_ready ?? false;
  const winColor =
    winRate > 55
      ? "text-emerald-400"
      : winRate >= 45
        ? "text-amber-400"
        : "text-red-400";

  const barData = data
    ? [
        {
          label: "Winners",
          score: data.avg_sentiment_score_winners,
        },
        {
          label: "Losers",
          score: data.avg_sentiment_score_losers,
        },
      ]
    : [];

  return (
    <PageShell title="Strategy validation">
      <div className="space-y-6">
        {/* Banner */}
        {data && (
          <FadeIn>
            <ValidationBanner
              current={data.total_sentiment_trades}
              target={30}
              isReady={data.is_statistically_ready}
            />
          </FadeIn>
        )}

        {data?.strategy_decay?.is_decaying && (
          <FadeIn>
            <div className="rounded-md border border-red-800 bg-red-950/50 p-4">
              <div className="flex items-start gap-3">
                <span className="text-red-400 mt-0.5 shrink-0">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                </span>
                <div>
                  <p className="text-[13px] font-medium text-red-300">Strategy decay detected</p>
                  <p className="text-[12px] text-red-400/80 mt-0.5">{data.strategy_decay.message}</p>
                  <div className="flex gap-4 mt-2 text-[11px] text-zinc-400">
                    <span>Recent win rate: <span className="text-red-300">{data.strategy_decay.recent_win_rate.toFixed(1)}%</span></span>
                    <span>All-time win rate: <span className="text-zinc-300">{data.strategy_decay.all_time_win_rate.toFixed(1)}%</span></span>
                    <span>Drop: <span className="text-red-400">{data.strategy_decay.drop_pct_points.toFixed(1)}pp</span></span>
                  </div>
                </div>
              </div>
            </div>
          </FadeIn>
        )}

        {/* Win rate */}
        <FadeIn delay={0.1}>
          <div className="rounded-md border border-zinc-800 p-6 bg-zinc-900 text-center">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-1">
              Sentiment strategy win rate
            </p>
            {isLoading ? (
              <Skeleton className="h-8 w-24 mx-auto bg-zinc-800" />
            ) : (
              <>
                <p className={`text-[28px] font-medium ${showColor ? winColor : "text-zinc-400"}`}>
                  {winRate.toFixed(1)}%
                </p>
                {!showColor && (
                  <p className="text-[11px] text-zinc-600 mt-1">
                    Insufficient sample — color-coding activates at 30+ trades.
                  </p>
                )}
              </>
            )}
          </div>
        </FadeIn>

        {/* KPI row */}
        <FadeIn delay={0.2}>
          <div className="grid grid-cols-4 gap-4">
            <KpiCard
              label="Avg win amount"
              value={data?.avg_win_amount ?? 0}
              format="currency"
              loading={isLoading}
            />
            <KpiCard
              label="Avg loss amount"
              value={data?.avg_loss_amount ?? 0}
              format="currency"
              loading={isLoading}
            />
            <KpiCard
              label="Total P&L"
              value={data?.total_pnl ?? 0}
              format="currency"
              loading={isLoading}
            />
            <KpiCard
              label="Total trades"
              value={data?.total_sentiment_trades ?? 0}
              format="number"
              loading={isLoading}
            />
          </div>
        </FadeIn>

        {/* Sentiment score comparison chart */}
        <FadeIn delay={0.3}>
          <div className="rounded-md border border-zinc-800 p-4 bg-zinc-900">
            <p className="text-[11px] uppercase text-zinc-500 tracking-wider mb-3">
              Sentiment conviction: winners vs losers
            </p>
            {isLoading ? (
              <Skeleton className="h-[200px] bg-zinc-800" />
            ) : barData.length > 0 ? (
              <div className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData}>
                    <XAxis
                      dataKey="label"
                      stroke="rgba(255,255,255,0.2)"
                      tick={{ fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      stroke="rgba(255,255,255,0.2)"
                      tick={{ fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      width={40}
                      domain={[-1, 1]}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #27272a",
                        borderRadius: "6px",
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                      <defs>
                        <linearGradient id="winGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity={0.8} />
                          <stop offset="100%" stopColor="#10b981" stopOpacity={0.3} />
                        </linearGradient>
                        <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#ef4444" stopOpacity={0.8} />
                          <stop offset="100%" stopColor="#ef4444" stopOpacity={0.3} />
                        </linearGradient>
                      </defs>
                      <Bar
                        dataKey="score"
                        fill="url(#winGrad)"
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-zinc-500 text-[13px] text-center py-8">
                Not enough data yet
              </p>
            )}
            <p className="text-[11px] text-zinc-600 mt-2 text-center">
              If winners show meaningfully stronger sentiment scores than losers, the signal has real predictive value.
            </p>
          </div>
        </FadeIn>
      </div>
    </PageShell>
  );
}
