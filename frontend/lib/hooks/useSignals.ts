"use client";

import { useQuery } from "@tanstack/react-query";
import api from "../api";
import type { SignalResponse } from "../types";

export function useLatestSignals() {
  return useQuery<SignalResponse[]>({
    queryKey: ["signals-latest"],
    queryFn: () => api.getLatestSignals(),
  });
}

export function useSignalsSummary() {
  return useQuery<any>({
    queryKey: ["signals-summary"],
    queryFn: () => api.getSignalsSummary(),
  });
}
