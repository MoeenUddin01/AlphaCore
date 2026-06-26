"use client";

import { useQuery } from "@tanstack/react-query";
import api from "../api";
import type {
  PerformanceMetricsResponse,
  PortfolioSnapshotResponse,
  WalletResponse,
} from "../types";

export function usePortfolioHistory(limit?: number) {
  return useQuery<PortfolioSnapshotResponse[]>({
    queryKey: ["portfolio-history", limit],
    queryFn: () => api.getPortfolioHistory(limit),
  });
}

export function usePortfolioMetrics() {
  return useQuery<PerformanceMetricsResponse>({
    queryKey: ["portfolio-metrics"],
    queryFn: () => api.getPortfolioMetrics(),
  });
}

export function usePositions() {
  return useQuery<any[]>({
    queryKey: ["positions"],
    queryFn: () => api.getPositions(),
  });
}

export function useWallet() {
  return useQuery<WalletResponse>({
    queryKey: ["wallet"],
    queryFn: () => api.getWallet(),
    refetchInterval: 60_000,
  });
}
