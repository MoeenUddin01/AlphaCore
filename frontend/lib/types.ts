export interface SignalResponse {
  symbol: string;
  predicted_return: number;
  direction: "up" | "down";
  confidence: number;
  sentiment_score: number;
  sentiment_label: string;
  fear_greed_value: number;
  has_holding: boolean;
  distance_to_threshold: number;
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

export interface StrategyDecayInfo {
  recent_win_rate: number;
  all_time_win_rate: number;
  drop_pct_points: number;
  recent_trades_count: number;
  is_decaying: boolean;
  message: string;
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
  strategy_decay: StrategyDecayInfo;
}

export interface HoldingResponse {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  current_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface ClosedTradeResponse {
  symbol: string;
  buy_price: number;
  sell_price: number;
  quantity: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  opened_at: string;
  closed_at: string;
  is_pre_fix_artifact: boolean;
}

export interface WalletResponse {
  cash_balance: number;
  total_holdings_value: number;
  total_unrealized_pnl: number;
  total_realized_pnl: number;
  holdings: HoldingResponse[];
  closed_positions: ClosedTradeResponse[];
}

export interface HealthResponse {
  status: string;
  database: boolean;
  timestamp: string;
  version: string;
}

export interface TradingStatusResponse {
  is_paused: boolean;
  status: string;
}
