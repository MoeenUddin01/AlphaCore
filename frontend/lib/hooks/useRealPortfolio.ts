"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../api";
import type {
  RealPortfolioSnapshotResponse,
  RealPositionResponse,
  RealSafetyStatusResponse,
  RealTradeResponse,
} from "../types";

export function useRealSafetyStatus() {
  return useQuery<RealSafetyStatusResponse>({
    queryKey: ["real-safety-status"],
    queryFn: () => api.getRealSafetyStatus(),
    refetchInterval: 30_000,
  });
}

export function useRealToggleKillSwitch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ halted, confirm }: { halted: boolean; confirm: string }) =>
      api.toggleRealKillSwitch(halted, confirm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["real-safety-status"] });
    },
  });
}

export function useRealPortfolioLatest() {
  return useQuery<RealPortfolioSnapshotResponse | null>({
    queryKey: ["real-portfolio-latest"],
    queryFn: () => api.getRealPortfolioLatest(),
    refetchInterval: 60_000,
  });
}

export function useRealPositions() {
  return useQuery<RealPositionResponse[]>({
    queryKey: ["real-positions"],
    queryFn: () => api.getRealPositions(),
    refetchInterval: 60_000,
  });
}

export function useRealTradeHistory(limit?: number, symbol?: string) {
  return useQuery<RealTradeResponse[]>({
    queryKey: ["real-trade-history", limit, symbol],
    queryFn: () => api.getRealTradeHistory(limit, symbol),
  });
}
