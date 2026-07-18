import type {
  HealthResponse,
  PortfolioSnapshotResponse,
  PerformanceMetricsResponse,
  RealPortfolioSnapshotResponse,
  RealPositionResponse,
  RealSafetyStatusResponse,
  RealTradeResponse,
  SentimentValidationResponse,
  SignalResponse,
  TradeResponse,
  TradingStatusResponse,
  WalletResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      "ngrok-skip-browser-warning": "true",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status} ${res.statusText} — ${path}`);
  }
  return res.json() as Promise<T>;
}

const api = {
  getHealth(): Promise<HealthResponse> {
    return fetchApi<HealthResponse>("/health");
  },

  getPortfolioHistory(limit = 50): Promise<PortfolioSnapshotResponse[]> {
    return fetchApi<PortfolioSnapshotResponse[]>(
      `/portfolio/history?limit=${limit}`
    );
  },

  getPortfolioMetrics(): Promise<PerformanceMetricsResponse> {
    return fetchApi<PerformanceMetricsResponse>("/portfolio/metrics");
  },

  getPortfolioCycles(limit = 20): Promise<any[]> {
    return fetchApi<any[]>(`/portfolio/cycles?limit=${limit}`);
  },

  getPositions(): Promise<any[]> {
    return fetchApi<any[]>("/portfolio/positions");
  },

  getSentimentValidation(
    days = 30
  ): Promise<SentimentValidationResponse> {
    return fetchApi<SentimentValidationResponse>(
      `/portfolio/sentiment-validation?days=${days}`
    );
  },

  getLatestSignals(): Promise<SignalResponse[]> {
    return fetchApi<SignalResponse[]>("/signals/latest");
  },

  getSignalsSummary(): Promise<any> {
    return fetchApi<any>("/signals/summary");
  },

  getTradeHistory(
    limit = 50,
    symbol?: string
  ): Promise<TradeResponse[]> {
    const query = symbol
      ? `/trades/history?limit=${limit}&symbol=${symbol}`
      : `/trades/history?limit=${limit}`;
    return fetchApi<TradeResponse[]>(query);
  },

  getTradeStats(): Promise<any> {
    return fetchApi<any>("/trades/stats");
  },

  getWallet(): Promise<WalletResponse> {
    return fetchApi<WalletResponse>("/portfolio/wallet");
  },

  pauseTrading(): Promise<any> {
    return fetchApi<any>("/portfolio/pause-trading", { method: "POST" });
  },

  resumeTrading(): Promise<any> {
    return fetchApi<any>("/portfolio/resume-trading", { method: "POST" });
  },

  getTradingStatus(): Promise<TradingStatusResponse> {
    return fetchApi<TradingStatusResponse>("/portfolio/trading-status");
  },

  sellPosition(symbol: string, quantity?: number): Promise<any> {
    return fetchApi<any>("/portfolio/sell", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, quantity: quantity ?? null }),
    });
  },

  // ── Real Account API ────────────────────────────────────────

  getRealSafetyStatus(): Promise<RealSafetyStatusResponse> {
    return fetchApi<RealSafetyStatusResponse>("/real/safety/status");
  },

  toggleRealKillSwitch(halted: boolean, confirm: string): Promise<any> {
    return fetchApi<any>("/real/safety/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ halted, confirm }),
    });
  },

  getRealPortfolioHistory(limit = 50): Promise<RealPortfolioSnapshotResponse[]> {
    return fetchApi<RealPortfolioSnapshotResponse[]>(
      `/real/portfolio/history?limit=${limit}`
    );
  },

  getRealPortfolioLatest(): Promise<RealPortfolioSnapshotResponse | null> {
    return fetchApi<RealPortfolioSnapshotResponse | null>("/real/portfolio/latest");
  },

  getRealPositions(): Promise<RealPositionResponse[]> {
    return fetchApi<RealPositionResponse[]>("/real/portfolio/positions");
  },

  getRealTradeHistory(
    limit = 50,
    symbol?: string
  ): Promise<RealTradeResponse[]> {
    const query = symbol
      ? `/real/trades/history?limit=${limit}&symbol=${symbol}`
      : `/real/trades/history?limit=${limit}`;
    return fetchApi<RealTradeResponse[]>(query);
  },

  getRealTradeStats(): Promise<any> {
    return fetchApi<any>("/real/trades/stats");
  },
};

export default api;
