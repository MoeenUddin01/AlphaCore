import type {
  HealthResponse,
  PortfolioSnapshotResponse,
  PerformanceMetricsResponse,
  SentimentValidationResponse,
  SignalResponse,
  TradeResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    cache: "no-store",
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

  pauseTrading(): Promise<any> {
    return fetchApi<any>("/portfolio/pause-trading", { method: "POST" });
  },

  resumeTrading(): Promise<any> {
    return fetchApi<any>("/portfolio/resume-trading", { method: "POST" });
  },
};

export default api;
