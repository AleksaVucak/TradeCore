import { api } from "./client";

export type User = { id: number; email: string };
export type Token = { access_token: string; token_type: string };
export type Symbol = { id: number; symbol: string; base_asset: string; quote_asset: string; is_active: boolean };
export type BacktestRunListItem = {
  id: string;
  symbol_id: number;
  symbol_name?: string | null;  // e.g. BTC (Phase 8.1)
  strategy_name?: string | null;  // e.g. My Strategy (Phase 8.1)
  timeframe: string;
  status: string;
  start_time: string;
  end_time: string;
  created_at: string;
  error_message?: string | null;  // Set when status is failed (Phase 7.3)
  total_return_pct?: number | null;  // From metrics when completed (Phase 8.1)
  max_drawdown_pct?: number | null;  // From metrics when completed (Phase 8.1)
};

export type TradeOut = {
  id: string;
  timestamp: string;
  side: string;
  price: number;
  quantity: number;
  fee: number;
  slippage: number;
  pnl: number | null;
};

export type EquityPointOut = {
  timestamp: string;
  equity_value: number;
};

export type BacktestRunDetail = {
  id: string;
  symbol_id: number;
  timeframe: string;
  status: string;
  start_time: string;
  end_time: string;
  created_at: string;
  error_message: string | null;
  trades: TradeOut[];
  equity_curve: EquityPointOut[];
  metrics: Record<string, number> | null;
};
export type StrategyListItem = { id: number; name: string; strategy_type: string; created_at: string };

export type StrategyVersion = {
  id: number;
  version_number: number;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
};

export type StrategyDetail = {
  id: number;
  name: string;
  description: string | null;
  strategy_type: string;
  created_at: string;
  updated_at: string;
  versions: StrategyVersion[];
};

export const authApi = {
  register: (email: string, password: string) =>
    api.post<User>("/api/v1/auth/register", { email, password }),
  login: (email: string, password: string) =>
    api.post<Token>("/api/v1/auth/login", new URLSearchParams({ username: email, password })),
  me: (token: string) => api.get<User>("/api/v1/auth/me", token),
};

export const symbolsApi = {
  list: () => api.get<Symbol[]>("/api/v1/symbols"),
};

export type RiskMetricsResponse = {
  run_id: string;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  total_return_pct: number;
  annualized_return_pct: number;
  max_drawdown_pct: number;
  avg_drawdown_pct: number;
  var_95: number;
  var_99: number;
  cvar_95: number;
  cvar_99: number;
  num_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  avg_trade_pnl: number;
  initial_equity: number;
  final_equity: number;
};

export const backtestsApi = {
  list: (token: string) => api.get<BacktestRunListItem[]>("/api/v1/backtests", token),
  get: (token: string, runId: string) =>
    api.get<BacktestRunDetail>(`/api/v1/backtests/${runId}`, token),
  getTrades: (token: string, runId: string) =>
    api.get<TradeOut[]>(`/api/v1/backtests/${runId}/trades`, token),
  getEquity: (token: string, runId: string) =>
    api.get<EquityPointOut[]>(`/api/v1/backtests/${runId}/equity`, token),
  getMetrics: (token: string, runId: string) =>
    api.get<Record<string, number>>(`/api/v1/backtests/${runId}/metrics`, token),
  getRiskMetrics: (token: string, runId: string) =>
    api.get<RiskMetricsResponse>(`/api/v1/backtests/${runId}/risk-metrics`, token),
};

export const strategiesApi = {
  list: (token: string) => api.get<StrategyListItem[]>("/api/v1/strategies", token),
  create: (
    token: string,
    body: {
      name: string;
      description?: string | null;
      strategy_type: string;
      config: Record<string, unknown>;
    }
  ) => api.post<StrategyDetail>("/api/v1/strategies", body, token),
  get: (token: string, id: number) =>
    api.get<StrategyDetail>(`/api/v1/strategies/${id}`, token),
  update: (
    token: string,
    id: number,
    body: { name?: string; description?: string | null }
  ) => api.patch<StrategyDetail>(`/api/v1/strategies/${id}`, body, token),
  createVersion: (
    token: string,
    id: number,
    body: { config: Record<string, unknown> }
  ) => api.post<StrategyDetail>(`/api/v1/strategies/${id}/versions`, body, token),
};

export type IngestResponse = { message: string; task_id: string | null };
export type CandleResponse = {
  id: number;
  symbol_id: number;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type RegimeLabelOut = {
  timestamp: string;
  regime: string;
};

export type RegimeLabelResponse = {
  model_id: number | null;
  symbol_id: number;
  timeframe: string;
  labels: RegimeLabelOut[];
};

export type RegimePerformanceItem = {
  regime: string;
  label: string;
  bars: number;
  bars_pct: number;
  num_trades: number;
  total_pnl: number;
  avg_pnl: number | null;
  win_rate: number | null;
  wins: number;
  losses: number;
};

export type RegimePerformanceResponse = {
  run_id: string;
  total_bars: number;
  total_trades_matched: number;
  regimes: RegimePerformanceItem[];
};

export type ModelInfoOut = {
  id: number;
  name: string;
  symbol_id: number | null;
  timeframe: string | null;
  training_start: string | null;
  training_end: string | null;
  created_at: string;
  accuracy: number | null;
  n_train: number | null;
  n_test: number | null;
  tuned: boolean;
  best_params: Record<string, unknown> | null;
  cv_best_score: number | null;
  cv_folds: number | null;
};

export type ModelListResponse = {
  models: ModelInfoOut[];
};

export const regimesApi = {
  getForRun: (token: string, runId: string) =>
    api.get<RegimeLabelResponse>(`/api/v1/regimes/run/${runId}`, token),
  get: (
    token: string,
    params: { symbol_id: number; timeframe: string; start?: string; end?: string; model_id?: number }
  ) => {
    const search = new URLSearchParams({
      symbol_id: String(params.symbol_id),
      timeframe: params.timeframe,
    });
    if (params.start) search.set("start", params.start);
    if (params.end) search.set("end", params.end);
    if (params.model_id != null) search.set("model_id", String(params.model_id));
    return api.get<RegimeLabelResponse>(`/api/v1/regimes?${search}`, token);
  },
  getPerformanceForRun: (token: string, runId: string) =>
    api.get<RegimePerformanceResponse>(`/api/v1/regimes/run/${runId}/performance`, token),
  getModelForRun: (token: string, runId: string) =>
    api.get<ModelInfoOut>(`/api/v1/regimes/run/${runId}/model`, token),
  listModels: (token: string, params?: { symbol_id?: number; timeframe?: string }) => {
    const search = new URLSearchParams();
    if (params?.symbol_id != null) search.set("symbol_id", String(params.symbol_id));
    if (params?.timeframe) search.set("timeframe", params.timeframe);
    const qs = search.toString();
    return api.get<ModelListResponse>(`/api/v1/regimes/models${qs ? `?${qs}` : ""}`, token);
  },
};

export const marketDataApi = {
  ingest: (
    token: string,
    body: { symbol_id: number; timeframe: string; start_date: string; end_date: string }
  ) => api.post<IngestResponse>("/api/v1/market-data/ingest", body, token),
  candles: (
    token: string,
    params: { symbol_id: number; timeframe: string; start: string; end: string; limit?: number }
  ) => {
    const search = new URLSearchParams({
      symbol_id: String(params.symbol_id),
      timeframe: params.timeframe,
      start: params.start,
      end: params.end,
    });
    if (params.limit != null) search.set("limit", String(params.limit));
    return api.get<CandleResponse[]>(`/api/v1/market-data/candles?${search}`, token);
  },
};
