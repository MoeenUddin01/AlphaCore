export interface SignalResponse {
  symbol: string;
  predicted_return: number;
  direction: "up" | "down";
  confidence: number;
  sentiment_score: number;
  sentiment_label: string;
  fear_greed_value: number;
  created_at: string;
}

export interface TradeResponse {
  id: string;
  cycle_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  proposed_quantity: number;
  executed_quantity: number | null;
  entry_price: number;
  executed_price: number | null;
  stop_loss_price: number;
  take_profit_price: number;
  order_id: string | null;
  status: "FILLED" | "FAILED" | "REJECTED_LOT_SIZE";
  reasoning: string;
  pnl: number | null;
  is_sentiment_driven: boolean;
  fee_paid: number | null;
  created_at: string;
}

export interface PortfolioSnapshotResponse {
  cycle_id: string;
  total_value: number;
  cash: number;
  positions_value: number;
  unrealised_pnl: number;
  realised_pnl: number;
  peak_value: number;
  drawdown_pct: number;
  created_at: string;
}

export interface PerformanceMetricsResponse {
  total_trades: number;
  win_rate: number;
  avg_pnl_per_trade: number;
  best_trade: number;
  worst_trade: number;
  total_realised_pnl: number;
  current_drawdown: number;
}

export interface SentimentValidationResponse {
  total_sentiment_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  avg_win_amount: number;
  avg_loss_amount: number;
  total_pnl: number;
  avg_sentiment_score_winners: number;
  avg_sentiment_score_losers: number;
  is_statistically_ready: boolean;
}

export interface HealthResponse {
  status: string;
  database: boolean;
  timestamp: string;
  version: string;
}
