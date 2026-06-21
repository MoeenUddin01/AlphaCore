"use client";

import { useQuery } from "@tanstack/react-query";
import api from "../api";
import type { TradeResponse } from "../types";

export function useTradeHistory(limit?: number, symbol?: string) {
  return useQuery<TradeResponse[]>({
    queryKey: ["trades", limit, symbol],
    queryFn: () => api.getTradeHistory(limit, symbol),
  });
}

export function useTradeStats() {
  return useQuery<any>({
    queryKey: ["trade-stats"],
    queryFn: () => api.getTradeStats(),
  });
}
