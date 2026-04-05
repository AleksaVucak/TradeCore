import { api } from "./client";

export type User = { id: number; email: string; email_verified: boolean; totp_enabled: boolean };
export type Token = { access_token: string; token_type: string };
export type RegisterResponse = { id: number; email: string; email_verified: boolean; message: string };
export type VerifyEmailResponse = { message: string; email_verified: boolean };
export type ResendVerificationResponse = { message: string };
export type TwoFactorSetupStartResponse = { secret: string; otpauth_uri: string };
export type TwoFactorSetupConfirmResponse = { message: string; totp_enabled: boolean };
export type TwoFactorDisableResponse = { message: string; totp_enabled: boolean };
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
export type CreateBacktestRequest = {
  strategy_version_id: number;
  symbol_id: number;
  timeframe: string;
  start_time: string;
  end_time: string;
  initial_equity: number;
};
export type WalkForwardValidationRequest = {
  strategy_version_id: number;
  symbol_id: number;
  timeframe: string;
  start_time: string;
  end_time: string;
  initial_equity: number;
  window_bars: number;
  step_bars: number;
};
export type WalkForwardWindow = {
  window_index: number;
  start_time: string;
  end_time: string;
  num_candles: number;
  num_trades: number;
  initial_equity: number;
  final_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
};
export type WalkForwardSummary = {
  total_windows: number;
  window_bars: number;
  step_bars: number;
  profitable_windows: number;
  profitable_window_pct: number;
  avg_total_return_pct: number;
  best_total_return_pct: number;
  worst_total_return_pct: number;
  avg_max_drawdown_pct: number;
  avg_sharpe_ratio: number;
};
export type WalkForwardValidationResponse = {
  strategy_version_id: number;
  symbol_id: number;
  timeframe: string;
  start_time: string;
  end_time: string;
  initial_equity: number;
  window_bars: number;
  step_bars: number;
  windows: WalkForwardWindow[];
  summary: WalkForwardSummary;
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
    api.post<RegisterResponse>("/api/v1/auth/register", { email, password }),
  login: (email: string, password: string, totpCode?: string) => {
    const params = new URLSearchParams({ username: email, password });
    if (totpCode) params.set("totp_code", totpCode);
    return api.post<Token>("/api/v1/auth/login", params);
  },
  me: (token: string) => api.get<User>("/api/v1/auth/me", token),
  verifyEmail: (token: string) =>
    api.post<VerifyEmailResponse>("/api/v1/auth/verify-email", { token }),
  resendVerification: (email: string, password: string) =>
    api.post<ResendVerificationResponse>("/api/v1/auth/resend-verification", { email, password }),
  twoFactorSetupStart: (token: string) =>
    api.post<TwoFactorSetupStartResponse>("/api/v1/auth/2fa/setup/start", {}, token),
  twoFactorSetupConfirm: (code: string, token: string) =>
    api.post<TwoFactorSetupConfirmResponse>("/api/v1/auth/2fa/setup/confirm", { code }, token),
  twoFactorDisable: (password: string, code: string, token: string) =>
    api.post<TwoFactorDisableResponse>("/api/v1/auth/2fa/disable", { password, code }, token),
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

export type BenchmarkPointOut = {
  timestamp: string;
  equity_value: number;
};

export type BenchmarkResponse = {
  run_id: string;
  equity_curve: BenchmarkPointOut[];
  initial_equity: number;
  final_equity: number;
  total_return_pct: number;
  strategy_return_pct: number;
  alpha_pct: number;
};

/** Phase 14.3: POST /backtests/{id}/monte-carlo */
export type MonteCarloRequest = {
  num_simulations?: number;
  method?: "bootstrap" | "shuffle";
  seed?: number | null;
};

export type MonteCarloPercentilePointOut = {
  step_index: number;
  p5_equity: number;
  p50_equity: number;
  p95_equity: number;
};

/** Phase 14.4: binned distribution for histograms */
export type MonteCarloHistogramBinOut = {
  bin_start: number;
  bin_end: number;
  count: number;
};

/** Central percentile bands over simulated outcomes (not a parametric CI). */
export type MonteCarloConfidenceIntervalsOut = {
  return_pct_ci_90_low: number;
  return_pct_ci_90_high: number;
  return_pct_ci_95_low: number;
  return_pct_ci_95_high: number;
  final_equity_ci_90_low: number;
  final_equity_ci_90_high: number;
  final_equity_ci_95_low: number;
  final_equity_ci_95_high: number;
};

export type MonteCarloResponse = {
  run_id: string;
  method: "bootstrap" | "shuffle";
  num_simulations: number;
  num_closed_trades: number;
  initial_equity: number;
  seed: number | null;
  mean_final_equity: number;
  median_final_equity: number;
  p5_final_equity: number;
  p95_final_equity: number;
  best_final_equity: number;
  worst_final_equity: number;
  mean_total_return_pct: number;
  median_total_return_pct: number;
  p5_total_return_pct: number;
  p95_total_return_pct: number;
  best_total_return_pct: number;
  worst_total_return_pct: number;
  mean_max_drawdown_pct: number;
  median_max_drawdown_pct: number;
  p95_max_drawdown_pct: number;
  worst_max_drawdown_pct: number;
  probability_profit_pct: number;
  probability_loss_pct: number;
  probability_drawdown_gt_10_pct: number;
  original_total_return_pct: number | null;
  percentile_equity_band: MonteCarloPercentilePointOut[];
  histogram_return_pct: MonteCarloHistogramBinOut[];
  histogram_final_equity: MonteCarloHistogramBinOut[];
  confidence_intervals: MonteCarloConfidenceIntervalsOut;
};

export const backtestsApi = {
  list: (token: string) => api.get<BacktestRunListItem[]>("/api/v1/backtests", token),
  create: (token: string, body: CreateBacktestRequest) =>
    api.post<BacktestRunDetail>("/api/v1/backtests", body, token),
  runWalkForward: (token: string, body: WalkForwardValidationRequest) =>
    api.post<WalkForwardValidationResponse>("/api/v1/backtests/walk-forward", body, token),
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
  getBenchmark: (token: string, runId: string) =>
    api.get<BenchmarkResponse>(`/api/v1/backtests/${runId}/benchmark`, token),
  postMonteCarlo: (
    token: string,
    runId: string,
    body: MonteCarloRequest = {}
  ) =>
    api.post<MonteCarloResponse>(
      `/api/v1/backtests/${runId}/monte-carlo`,
      body,
      token
    ),
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

export type CoverageRangeResponse = {
  symbol_id: number;
  timeframe: string;
  start_date: string;
  end_date: string;
  candle_count: number;
};

export type FetchRequest = {
  symbol_id: number;
  timeframe: string;
  start_date: string;
  end_date: string;
};

export type FetchJobResponse = {
  job_id: string;
  status: string;
  symbol_id: number;
  timeframe: string;
  start_date: string;
  end_date: string;
  created_at: string;
  message: string;
};

export type FetchJobStatusResponse = {
  job_id: string;
  status: string;
  symbol_id: number;
  timeframe: string;
  start_date: string;
  end_date: string;
  total_chunks: number;
  completed_chunks: number;
  candles_fetched: number;
  progress_pct: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
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

export type EnsureRegimesResponse = {
  status: string;
  labeled_bars: number;
  model_id: number | null;
};

export type TrainRegimeRequest = {
  symbol_id: number;
  timeframe: string;
  start?: string | null;
  end?: string | null;
  tune?: boolean;
};

export type TrainRegimeResponse = {
  status: string;
  task_id: string;
};

export const regimesApi = {
  train: (token: string, body: TrainRegimeRequest) =>
    api.post<TrainRegimeResponse>("/api/v1/regimes/train", body, token),
  ensureForRun: (token: string, runId: string) =>
    api.post<EnsureRegimesResponse>(`/api/v1/regimes/run/${runId}/ensure`, {}, token),
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
  fetch: (token: string, body: FetchRequest) =>
    api.post<FetchJobResponse>("/api/v1/market-data/fetch", body, token),
  getFetchJob: (token: string, jobId: string) =>
    api.get<FetchJobStatusResponse>(`/api/v1/market-data/fetch/${jobId}`, token),
  listFetchJobs: (
    token: string,
    params?: { status?: string; limit?: number }
  ) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.limit != null) search.set("limit", String(params.limit));
    const qs = search.toString();
    return api.get<FetchJobStatusResponse[]>(
      `/api/v1/market-data/fetch${qs ? `?${qs}` : ""}`,
      token
    );
  },
  coverage: (
    token: string,
    params?: { symbol_id?: number; timeframe?: string }
  ) => {
    const search = new URLSearchParams();
    if (params?.symbol_id != null) search.set("symbol_id", String(params.symbol_id));
    if (params?.timeframe) search.set("timeframe", params.timeframe);
    const qs = search.toString();
    return api.get<CoverageRangeResponse[]>(
      `/api/v1/market-data/coverage${qs ? `?${qs}` : ""}`,
      token
    );
  },
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
