"use client";

import { useState } from "react";
import { useRealSafetyStatus, useRealToggleKillSwitch } from "@/lib/hooks/useRealPortfolio";
import PageShell from "@/components/layout/PageShell";
import FadeIn from "@/components/motion/FadeIn";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function RealPage() {
  const { data: safety, isLoading, error } = useRealSafetyStatus();
  const toggle = useRealToggleKillSwitch();
  const [confirmText, setConfirmText] = useState("");

  const halted = safety?.trading_halted ?? true;

  const handleToggle = () => {
    if (confirmText !== "CONFIRM") return;
    toggle.mutate({ halted: !halted, confirm: "CONFIRM" });
    setConfirmText("");
  };

  return (
    <PageShell title="Real Account">
      {/* LIVE MONEY banner */}
      <div className="mb-6 rounded-md border-2 border-red-600 bg-red-950/40 px-5 py-3 text-center text-sm font-bold tracking-wider text-red-400">
        ⚠  REAL — LIVE MONEY  ⚠
      </div>

      {/* Kill switch */}
      <FadeIn>
        <div className="mb-6 rounded-md border border-zinc-800 bg-zinc-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">
              Kill Switch
            </p>
            {isLoading ? (
              <Skeleton className="h-6 w-24 bg-zinc-800" />
            ) : (
              <Badge className={halted ? "bg-red-600" : "bg-emerald-600"}>
                {halted ? "HALTED" : "ACTIVE"}
              </Badge>
            )}
          </div>

          {error && (
            <p className="mb-3 text-[13px] text-red-400">
              Failed to load safety status — check API.
            </p>
          )}

          <input
            type="text"
            placeholder='Type CONFIRM to toggle'
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            className="mb-3 w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-[13px] text-zinc-200 placeholder-zinc-500"
          />
          <button
            onClick={handleToggle}
            disabled={confirmText !== "CONFIRM" || toggle.isPending}
            className={`rounded px-4 py-2 text-[13px] font-medium text-white transition-opacity ${
              halted
                ? "bg-emerald-600 hover:bg-emerald-500"
                : "bg-red-600 hover:bg-red-500"
            } disabled:opacity-40`}
          >
            {toggle.isPending
              ? "Updating…"
              : halted
                ? "Enable Trading"
                : "Halt Trading"}
          </button>
          {toggle.isSuccess && (
            <p className="mt-2 text-[12px] text-emerald-400">Kill switch updated.</p>
          )}
          {toggle.isError && (
            <p className="mt-2 text-[12px] text-red-400">Failed to update kill switch.</p>
          )}
        </div>
      </FadeIn>

      {/* Limits + usage */}
      <FadeIn delay={0.1}>
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">
              Max Position
            </p>
            {isLoading ? (
              <Skeleton className="mt-1 h-5 w-20 bg-zinc-800" />
            ) : (
              <p className="mt-1 text-[15px] font-medium text-zinc-200">
                ${safety?.limits.max_position_usd.toFixed(2) ?? "—"}
              </p>
            )}
          </div>
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">
              Daily Loss
            </p>
            {isLoading ? (
              <Skeleton className="mt-1 h-5 w-24 bg-zinc-800" />
            ) : (
              <p
                className={`mt-1 text-[15px] font-medium ${
                  (safety?.daily_loss ?? 0) < 0 ? "text-red-400" : "text-zinc-200"
                }`}
              >
                ${safety?.daily_loss.toFixed(2) ?? "—"} / ${safety?.limits.max_daily_loss_usd.toFixed(2)}
              </p>
            )}
          </div>
          <div className="rounded-md border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">
              Trades Today
            </p>
            {isLoading ? (
              <Skeleton className="mt-1 h-5 w-16 bg-zinc-800" />
            ) : (
              <p className="mt-1 text-[15px] font-medium text-zinc-200">
                {safety?.trades_today ?? "—"} / {safety?.limits.max_trades_per_day}
              </p>
            )}
          </div>
        </div>
      </FadeIn>
    </PageShell>
  );
}
