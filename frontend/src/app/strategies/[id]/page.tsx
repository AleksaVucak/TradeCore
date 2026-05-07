"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  regimesApi,
  strategiesApi,
  symbolsApi,
  type ModelInfoOut,
  type StrategyDetail,
  type Symbol,
} from "@/lib/api/endpoints";
import { Progress } from "@/components/ui/progress";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// RSI+MA config form
// ---------------------------------------------------------------------------
type RsiMaConfigForm = {
  rsi_period: string;
  rsi_buy_threshold: string;
  rsi_sell_threshold: string;
  ma_period: string;
  position_size_pct: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  fee_rate: string;
  slippage_rate: string;
};

function rsiMaFormFromConfig(cfg: Record<string, unknown>): RsiMaConfigForm {
  return {
    rsi_period: String(cfg.rsi_period ?? 14),
    rsi_buy_threshold: String(cfg.rsi_buy_threshold ?? 50),
    rsi_sell_threshold: String(cfg.rsi_sell_threshold ?? 50),
    ma_period: String(cfg.ma_period ?? 20),
    position_size_pct: String(Number(cfg.position_size_pct ?? 1.0) * 100),
    stop_loss_pct: String(cfg.stop_loss_pct ?? 2.0),
    take_profit_pct: String(cfg.take_profit_pct ?? 5.0),
    fee_rate: String(cfg.fee_rate ?? 0.001),
    slippage_rate: String(cfg.slippage_rate ?? 0.0005),
  };
}

function rsiMaFormToPayload(f: RsiMaConfigForm): Record<string, unknown> {
  return {
    rsi_period: Number(f.rsi_period) || undefined,
    rsi_buy_threshold: Number(f.rsi_buy_threshold) || undefined,
    rsi_sell_threshold: Number(f.rsi_sell_threshold) || undefined,
    ma_period: Number(f.ma_period) || undefined,
    position_size_pct: f.position_size_pct.trim() === "" ? undefined : Number(f.position_size_pct) / 100,
    stop_loss_pct: Number(f.stop_loss_pct) || undefined,
    take_profit_pct: Number(f.take_profit_pct) || undefined,
    fee_rate: Number(f.fee_rate) || undefined,
    slippage_rate: Number(f.slippage_rate) || undefined,
  };
}

// ---------------------------------------------------------------------------
// ML Signal config form
// ---------------------------------------------------------------------------
type MlSignalConfigForm = {
  model_id: string;
  long_threshold: string;
  exit_threshold: string;
  position_size_pct: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  fee_rate: string;
  slippage_rate: string;
};

function mlSignalFormFromConfig(cfg: Record<string, unknown>): MlSignalConfigForm {
  return {
    model_id: String(cfg.model_id ?? ""),
    long_threshold: String(cfg.long_threshold ?? 0.55),
    exit_threshold: String(cfg.exit_threshold ?? 0.45),
    position_size_pct: String(Number(cfg.position_size_pct ?? 1.0) * 100),
    stop_loss_pct: String(cfg.stop_loss_pct ?? 3.0),
    take_profit_pct: String(cfg.take_profit_pct ?? 6.0),
    fee_rate: String(cfg.fee_rate ?? 0.001),
    slippage_rate: String(cfg.slippage_rate ?? 0.0005),
  };
}

function mlSignalFormToPayload(f: MlSignalConfigForm, features: string[]): Record<string, unknown> {
  return {
    model_id: Number(f.model_id),
    features,
    long_threshold: Number(f.long_threshold),
    exit_threshold: Number(f.exit_threshold),
    position_size_pct: f.position_size_pct.trim() === "" ? undefined : Number(f.position_size_pct) / 100,
    stop_loss_pct: Number(f.stop_loss_pct) || undefined,
    take_profit_pct: Number(f.take_profit_pct) || undefined,
    fee_rate: Number(f.fee_rate) || undefined,
    slippage_rate: Number(f.slippage_rate) || undefined,
  };
}

const DEFAULT_ML_FEATURES = [
  "rsi_14", "sma_20", "macd", "bbands_width", "atr_14", "log_return_1",
];

const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function StrategyDetailPage() {
  const router = useRouter();
  const pathname = usePathname();
  const idSegment = pathname.split("/").pop() || "";
  const strategyId = Number(idSegment);

  const [strategy, setStrategy] = useState<StrategyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [metaName, setMetaName] = useState("");
  const [metaDescription, setMetaDescription] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);

  // RSI+MA
  const [rsiForm, setRsiForm] = useState<RsiMaConfigForm | null>(null);

  // ML Signal config form
  const [mlForm, setMlForm] = useState<MlSignalConfigForm | null>(null);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>(DEFAULT_ML_FEATURES);
  const [featureCatalog, setFeatureCatalog] = useState<string[]>([]);
  // Only signal models are valid for backtesting; this list is pre-filtered
  const [signalModels, setSignalModels] = useState<ModelInfoOut[]>([]);

  const [savingConfig, setSavingConfig] = useState(false);

  // Signal model training state
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  // Symbol + timeframe the user wants to train on (independent of config's selected model)
  const [trainSymbolId, setTrainSymbolId] = useState<string>("");
  const [trainTimeframe, setTrainTimeframe] = useState<string>("1h");
  const [trainSubmitting, setTrainSubmitting] = useState(false);
  const [trainTune, setTrainTune] = useState(false);
  const [trainHorizon, setTrainHorizon] = useState("5");
  const [trainTaskId, setTrainTaskId] = useState<string | null>(null);
  const [trainState, setTrainState] = useState<string | null>(null);
  const [trainProgressPct, setTrainProgressPct] = useState<number | null>(null);
  const [trainPhase, setTrainPhase] = useState<string | null>(null);
  const [trainResult, setTrainResult] = useState<{
    accuracy: number | null;
    model_id: number | null;
    error: string | null;
  } | null>(null);
  // Shows a banner prompting the user to save after auto-selecting a new model
  const [newModelAutoSelected, setNewModelAutoSelected] = useState(false);
  const trainPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const hasValidParams = !!token && !!strategyId && !Number.isNaN(strategyId);

  useEffect(() => {
    Promise.resolve().then(() => setToken(getToken()));
  }, []);

  // Load symbols
  useEffect(() => {
    symbolsApi.list().then(setSymbols).catch(() => {});
  }, []);

  const stopTrainPolling = useCallback(() => {
    if (trainPollRef.current) {
      clearInterval(trainPollRef.current);
      trainPollRef.current = null;
    }
  }, []);

  // Fetches the signal-only model list and updates state
  const refreshSignalModels = useCallback(
    (t: string) => {
      regimesApi
        .listModels(t, { model_type: "signal" })
        .then((r) => setSignalModels(r.models))
        .catch(() => {});
    },
    [],
  );

  const startTrainPolling = useCallback(
    (taskId: string) => {
      stopTrainPolling();
      setTrainTaskId(taskId);
      setTrainState("PENDING");
      setTrainProgressPct(0);
      setTrainPhase("Queued");
      setTrainResult(null);
      setNewModelAutoSelected(false);

      trainPollRef.current = setInterval(async () => {
        const tok = getToken();
        if (!tok) return;
        try {
          const s = await strategiesApi.getSignalTrainStatus(tok, taskId);
          setTrainState(s.state);
          if (s.progress_pct != null) setTrainProgressPct(s.progress_pct);
          if (s.phase != null) setTrainPhase(s.phase);

          if (s.state === "SUCCESS" && !s.error) {
            stopTrainPolling();
            setTrainProgressPct(100);
            setTrainPhase("Complete");
            setTrainResult({ accuracy: s.accuracy, model_id: s.model_id, error: null });
            setTrainTaskId(null);

            // Refresh signal model list, then auto-select the newly trained model
            if (tok) {
              regimesApi
                .listModels(tok, { model_type: "signal" })
                .then((r) => {
                  setSignalModels(r.models);
                  if (s.model_id != null) {
                    setMlForm((prev) =>
                      prev ? { ...prev, model_id: String(s.model_id) } : prev,
                    );
                    setNewModelAutoSelected(true);
                  }
                })
                .catch(() => {});
            }
          } else if (s.state === "FAILURE" || s.error) {
            stopTrainPolling();
            setTrainProgressPct(null);
            setTrainPhase(null);
            setTrainResult({ accuracy: null, model_id: null, error: s.error || "Training failed" });
            setTrainTaskId(null);
          }
        } catch {
          // transient error — keep polling
        }
      }, 3000);
    },
    [stopTrainPolling],
  );

  useEffect(() => {
    return () => stopTrainPolling();
  }, [stopTrainPolling]);

  // Load strategy
  useEffect(() => {
    if (!hasValidParams || !token) return;
    strategiesApi
      .get(token, strategyId)
      .then((data) => {
        setStrategy(data);
        setMetaName(data.name);
        setMetaDescription(data.description ?? "");
        const cfg = (data.versions.find((v) => v.is_active) ?? data.versions[0])
          ?.config as Record<string, unknown> | undefined;

        if (data.strategy_type === "ml_signal" && cfg) {
          setMlForm(mlSignalFormFromConfig(cfg));
          const feats = cfg.features;
          if (Array.isArray(feats)) setSelectedFeatures(feats as string[]);
          setRsiForm(null);
        } else if (cfg) {
          setRsiForm(rsiMaFormFromConfig(cfg));
          setMlForm(null);
        }
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to load strategy.";
        setError(msg === "Not authenticated" ? "Please log in again." : msg);
      })
      .finally(() => setLoading(false));
  }, [strategyId, token, hasValidParams]);

  // Fetch ML metadata when strategy is ml_signal
  useEffect(() => {
    if (!token || !strategy || strategy.strategy_type !== "ml_signal") return;
    strategiesApi.mlFeatures(token).then(setFeatureCatalog).catch(() => {});
    refreshSignalModels(token);
  }, [token, strategy, refreshSignalModels]);

  // Pre-populate training symbol/timeframe from the model saved in config
  useEffect(() => {
    if (!mlForm?.model_id || signalModels.length === 0) return;
    const linked = signalModels.find((m) => m.id === Number(mlForm.model_id));
    if (!linked) return;
    if (linked.symbol_id != null && !trainSymbolId) {
      setTrainSymbolId(String(linked.symbol_id));
    }
    if (linked.timeframe && trainTimeframe === "1h") {
      setTrainTimeframe(linked.timeframe);
    }
  // Only run when mlForm.model_id or signalModels first become available
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mlForm?.model_id, signalModels]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  function handleMetaSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!strategy || !token) return;
    setSavingMeta(true);
    setError(null);
    strategiesApi
      .update(token, strategy.id, {
        name: metaName.trim() || undefined,
        description: metaDescription.trim() || null,
      })
      .then((updated) => setStrategy(updated))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to update strategy."))
      .finally(() => setSavingMeta(false));
  }

  function handleRsiChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name: field, value } = e.target;
    setRsiForm((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  function handleMlChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name: field, value } = e.target;
    setMlForm((prev) => (prev ? { ...prev, [field]: value } : prev));
    // Clear auto-select banner if the user manually changes the model
    if (field === "model_id") setNewModelAutoSelected(false);
  }

  function toggleFeature(feat: string) {
    setSelectedFeatures((prev) =>
      prev.includes(feat) ? prev.filter((f) => f !== feat) : [...prev, feat],
    );
  }

  function handleConfigSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!strategy || !token) return;
    setSavingConfig(true);
    setError(null);

    let configPayload: Record<string, unknown>;
    if (strategy.strategy_type === "ml_signal" && mlForm) {
      if (!mlForm.model_id) {
        setError("Please select a trained signal model.");
        setSavingConfig(false);
        return;
      }
      if (selectedFeatures.length === 0) {
        setError("Please select at least one feature.");
        setSavingConfig(false);
        return;
      }
      configPayload = mlSignalFormToPayload(mlForm, selectedFeatures);
    } else if (rsiForm) {
      configPayload = rsiMaFormToPayload(rsiForm);
    } else {
      setSavingConfig(false);
      return;
    }

    strategiesApi
      .createVersion(token, strategy.id, { config: configPayload })
      .then((updated) => {
        setStrategy(updated);
        const cfg = (updated.versions.find((v) => v.is_active) ?? updated.versions[0])
          ?.config as Record<string, unknown> | undefined;
        if (!cfg) return;
        if (updated.strategy_type === "ml_signal") {
          setMlForm(mlSignalFormFromConfig(cfg));
          if (Array.isArray(cfg.features)) setSelectedFeatures(cfg.features as string[]);
          setNewModelAutoSelected(false);
        } else {
          setRsiForm(rsiMaFormFromConfig(cfg));
        }
        router.refresh();
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to create new version."))
      .finally(() => setSavingConfig(false));
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          <Link href="/strategies" className="text-muted-foreground hover:text-foreground text-sm">
            ← Back to strategies
          </Link>
          <h1 className="text-xl font-semibold tracking-tight mt-1">
            {strategy ? strategy.name : `Strategy ${idSegment}`}
          </h1>
        </div>
        {!!strategyId && !Number.isNaN(strategyId) && (
          <div className="mt-3 flex flex-wrap gap-4">
            <Link
              href={`/backtests/new?strategyId=${strategyId}`}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Run backtest with this strategy
            </Link>
            <Link
              href={`/backtests/walk-forward?strategyId=${strategyId}`}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Run walk-forward validation
            </Link>
          </div>
        )}
      </header>

      <main className="container mx-auto max-w-5xl px-6 py-8 space-y-6">
        {!hasValidParams && (
          <p className="text-sm text-destructive">Missing strategy id or not authenticated.</p>
        )}
        {error && hasValidParams && <p className="text-sm text-destructive">{error}</p>}

        {!hasValidParams ? (
          <p className="text-sm text-muted-foreground">
            Unable to load a strategy without a valid id and authentication.
          </p>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading strategy…</p>
        ) : !strategy ? (
          <p className="text-sm text-muted-foreground">Strategy not found.</p>
        ) : (
          <>
            {/* ---- Meta card ---- */}
            <Card>
              <CardHeader>
                <CardTitle>Strategy details</CardTitle>
                <CardDescription>
                  Edit the strategy&apos;s name and description. Type is fixed to the template used
                  when it was created.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form className="space-y-4" onSubmit={handleMetaSubmit}>
                  <div className="space-y-1.5 max-w-md">
                    <Label htmlFor="meta-name">Name</Label>
                    <Input
                      id="meta-name"
                      value={metaName}
                      onChange={(e) => setMetaName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="space-y-1.5 max-w-md">
                    <Label htmlFor="meta-description">Description</Label>
                    <Input
                      id="meta-description"
                      value={metaDescription}
                      onChange={(e) => setMetaDescription(e.target.value)}
                      placeholder="Optional description"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Type</Label>
                    <p className="text-sm text-muted-foreground uppercase">{strategy.strategy_type}</p>
                  </div>
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <Button type="submit" size="sm" disabled={savingMeta || !token}>
                      {savingMeta ? "Saving…" : "Save changes"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* ---- Config card ---- */}
            <Card>
              <CardHeader>
                <CardTitle>Active version config</CardTitle>
                <CardDescription>
                  Adjust parameters and save as a new version. The latest active version will be
                  used for backtests.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* RSI+MA config editor */}
                {strategy.strategy_type === "rsi_ma" && rsiForm && (
                  <form className="space-y-6" onSubmit={handleConfigSubmit}>
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">RSI</h2>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="rsi_period">RSI period</Label>
                          <Input
                            id="rsi_period"
                            name="rsi_period"
                            type="number"
                            min={2}
                            max={100}
                            value={rsiForm.rsi_period}
                            onChange={handleRsiChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="rsi_buy_threshold">Buy threshold</Label>
                          <Input
                            id="rsi_buy_threshold"
                            name="rsi_buy_threshold"
                            type="number"
                            min={0}
                            max={100}
                            value={rsiForm.rsi_buy_threshold}
                            onChange={handleRsiChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="rsi_sell_threshold">Sell threshold</Label>
                          <Input
                            id="rsi_sell_threshold"
                            name="rsi_sell_threshold"
                            type="number"
                            min={0}
                            max={100}
                            value={rsiForm.rsi_sell_threshold}
                            onChange={handleRsiChange}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Trend filter</h2>
                      <div className="space-y-1.5 max-w-xs">
                        <Label htmlFor="ma_period">MA period</Label>
                        <Input
                          id="ma_period"
                          name="ma_period"
                          type="number"
                          min={1}
                          max={500}
                          value={rsiForm.ma_period}
                          onChange={handleRsiChange}
                        />
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Position &amp; risk</h2>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="position_size_pct">Position size (%)</Label>
                          <Input
                            id="position_size_pct"
                            name="position_size_pct"
                            type="number"
                            min={0.01}
                            max={100}
                            step={0.01}
                            value={rsiForm.position_size_pct}
                            onChange={handleRsiChange}
                          />
                          <p className="text-xs text-muted-foreground">
                            Enter 100 to use the full account balance per trade.
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="stop_loss_pct">Stop loss (%)</Label>
                          <Input
                            id="stop_loss_pct"
                            name="stop_loss_pct"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            value={rsiForm.stop_loss_pct}
                            onChange={handleRsiChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="take_profit_pct">Take profit (%)</Label>
                          <Input
                            id="take_profit_pct"
                            name="take_profit_pct"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            value={rsiForm.take_profit_pct}
                            onChange={handleRsiChange}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="fee_rate">Fee rate (fraction)</Label>
                          <Input
                            id="fee_rate"
                            name="fee_rate"
                            type="number"
                            min={0}
                            max={1}
                            step={0.0001}
                            value={rsiForm.fee_rate}
                            onChange={handleRsiChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="slippage_rate">Slippage rate (fraction)</Label>
                          <Input
                            id="slippage_rate"
                            name="slippage_rate"
                            type="number"
                            min={0}
                            max={1}
                            step={0.0001}
                            value={rsiForm.slippage_rate}
                            onChange={handleRsiChange}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 pt-2">
                      <Button type="submit" size="sm" disabled={savingConfig || !token}>
                        {savingConfig ? "Saving…" : "Save as new version"}
                      </Button>
                    </div>
                  </form>
                )}

                {/* ML Signal config editor */}
                {strategy.strategy_type === "ml_signal" && mlForm && (
                  <form className="space-y-6" onSubmit={handleConfigSubmit}>
                    {/* Auto-select banner */}
                    {newModelAutoSelected && (
                      <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3">
                        <p className="text-sm text-blue-700 dark:text-blue-400">
                          New model trained and auto-selected below. Click &quot;Save as new version&quot; to
                          use it in backtests.
                        </p>
                      </div>
                    )}

                    {/* Model picker — signal models only */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Model</h2>
                      <div className="space-y-1.5 max-w-md">
                        <Label htmlFor="model_id">Trained signal model</Label>
                        <select
                          id="model_id"
                          name="model_id"
                          value={mlForm.model_id}
                          onChange={handleMlChange}
                          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <option value="">Select a signal model…</option>
                          {signalModels.map((m) => (
                            <option key={m.id} value={m.id}>
                              #{m.id} {m.name} — acc{" "}
                              {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "n/a"}{" "}
                              ({m.timeframe ?? "?"}) ·{" "}
                              {symbols.find((s) => s.id === m.symbol_id)?.symbol ?? `sym#${m.symbol_id}`}
                            </option>
                          ))}
                        </select>
                        {signalModels.length === 0 ? (
                          <p className="text-xs text-muted-foreground">
                            No trained signal models found. Use the &quot;Train signal model&quot; card
                            below to train one first.
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground">
                            Only signal models are shown. The model&apos;s features must match the
                            feature selection below.
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Feature selection */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Features</h2>
                      <p className="text-xs text-muted-foreground">
                        Select the features your model was trained on. These must exactly match the
                        feature set used during training.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {(featureCatalog.length > 0 ? featureCatalog : DEFAULT_ML_FEATURES).map((feat) => {
                          const active = selectedFeatures.includes(feat);
                          return (
                            <button
                              key={feat}
                              type="button"
                              onClick={() => toggleFeature(feat)}
                              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                                active
                                  ? "border-primary bg-primary/10 text-primary"
                                  : "border-input text-muted-foreground hover:bg-accent"
                              }`}
                            >
                              {feat}
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {selectedFeatures.length} feature{selectedFeatures.length !== 1 ? "s" : ""} selected
                      </p>
                    </div>

                    {/* Thresholds */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Signal thresholds</h2>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="long_threshold">Long threshold</Label>
                          <Input
                            id="long_threshold"
                            name="long_threshold"
                            type="number"
                            min={0}
                            max={1}
                            step={0.01}
                            value={mlForm.long_threshold}
                            onChange={handleMlChange}
                          />
                          <p className="text-xs text-muted-foreground">Enter long when P(up) &ge; this value</p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="exit_threshold">Exit threshold</Label>
                          <Input
                            id="exit_threshold"
                            name="exit_threshold"
                            type="number"
                            min={0}
                            max={1}
                            step={0.01}
                            value={mlForm.exit_threshold}
                            onChange={handleMlChange}
                          />
                          <p className="text-xs text-muted-foreground">Exit position when P(up) &le; this value</p>
                        </div>
                      </div>
                    </div>

                    {/* Position & risk */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Position &amp; risk</h2>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_position_size_pct">Position size (%)</Label>
                          <Input
                            id="ml_position_size_pct"
                            name="position_size_pct"
                            type="number"
                            min={0.01}
                            max={100}
                            step={0.01}
                            value={mlForm.position_size_pct}
                            onChange={handleMlChange}
                          />
                          <p className="text-xs text-muted-foreground">
                            Enter 100 to use the full account balance per trade.
                          </p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_stop_loss_pct">Stop loss (%)</Label>
                          <Input
                            id="ml_stop_loss_pct"
                            name="stop_loss_pct"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            value={mlForm.stop_loss_pct}
                            onChange={handleMlChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_take_profit_pct">Take profit (%)</Label>
                          <Input
                            id="ml_take_profit_pct"
                            name="take_profit_pct"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            value={mlForm.take_profit_pct}
                            onChange={handleMlChange}
                          />
                        </div>
                      </div>
                    </div>

                    {/* Execution */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_fee_rate">Fee rate (fraction)</Label>
                          <Input
                            id="ml_fee_rate"
                            name="fee_rate"
                            type="number"
                            min={0}
                            max={1}
                            step={0.0001}
                            value={mlForm.fee_rate}
                            onChange={handleMlChange}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_slippage_rate">Slippage rate (fraction)</Label>
                          <Input
                            id="ml_slippage_rate"
                            name="slippage_rate"
                            type="number"
                            min={0}
                            max={1}
                            step={0.0001}
                            value={mlForm.slippage_rate}
                            onChange={handleMlChange}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 pt-2">
                      <Button type="submit" size="sm" disabled={savingConfig || !token}>
                        {savingConfig ? "Saving…" : "Save as new version"}
                      </Button>
                    </div>
                  </form>
                )}

                {/* Unsupported type fallback */}
                {strategy.strategy_type !== "rsi_ma" && strategy.strategy_type !== "ml_signal" && (
                  <p className="text-sm text-muted-foreground">
                    Editing is not yet supported for &quot;{strategy.strategy_type}&quot; strategies.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* ---- Signal model training card (ML Signal only) ---- */}
            {strategy.strategy_type === "ml_signal" && (
              <Card>
                <CardHeader>
                  <CardTitle>Train signal model</CardTitle>
                  <CardDescription>
                    Train a new ML signal model on historical OHLCV data. After training completes, the
                    new model will be automatically selected in the config above — just save as a new
                    version to start using it.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  {/* Training target: symbol + timeframe */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-muted-foreground">Training data</h3>
                    <div className="flex flex-wrap gap-3">
                      <div className="space-y-1.5 min-w-[180px]">
                        <Label htmlFor="train-symbol">Symbol</Label>
                        <select
                          id="train-symbol"
                          value={trainSymbolId}
                          onChange={(e) => setTrainSymbolId(e.target.value)}
                          disabled={!!trainTaskId}
                          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
                        >
                          <option value="">Select symbol…</option>
                          {symbols.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.symbol}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1.5 min-w-[120px]">
                        <Label htmlFor="train-timeframe">Timeframe</Label>
                        <select
                          id="train-timeframe"
                          value={trainTimeframe}
                          onChange={(e) => setTrainTimeframe(e.target.value)}
                          disabled={!!trainTaskId}
                          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
                        >
                          {TIMEFRAME_OPTIONS.map((tf) => (
                            <option key={tf} value={tf}>
                              {tf}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1.5 min-w-[120px]">
                        <Label htmlFor="train-horizon">Prediction horizon (bars)</Label>
                        <Input
                          id="train-horizon"
                          type="number"
                          min={1}
                          max={50}
                          value={trainHorizon}
                          onChange={(e) => setTrainHorizon(e.target.value)}
                          className="w-28"
                          disabled={!!trainTaskId}
                        />
                      </div>

                      <label className="flex items-center gap-2 text-sm cursor-pointer self-end pb-1">
                        <input
                          type="checkbox"
                          checked={trainTune}
                          onChange={(e) => setTrainTune(e.target.checked)}
                          className="rounded border-input"
                          disabled={!!trainTaskId}
                        />
                        Hyperparameter tuning
                      </label>
                    </div>
                  </div>

                  {/* Features used for training */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-muted-foreground">Features to train on</h3>
                    <p className="text-xs text-muted-foreground">
                      Matches the feature selection in the config above. Adjust features there, then train.
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedFeatures.length > 0 ? (
                        selectedFeatures.map((f) => (
                          <span
                            key={f}
                            className="rounded-full border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
                          >
                            {f}
                          </span>
                        ))
                      ) : (
                        <p className="text-xs text-muted-foreground italic">
                          No features selected in config above.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Train button */}
                  <div>
                    <Button
                      disabled={trainSubmitting || !!trainTaskId || !trainSymbolId || selectedFeatures.length === 0}
                      onClick={async () => {
                        const t = getToken();
                        if (!t || !trainSymbolId) return;
                        setTrainSubmitting(true);
                        setError(null);
                        setTrainResult(null);
                        try {
                          const res = await strategiesApi.trainSignalModel(t, {
                            symbol_id: Number(trainSymbolId),
                            timeframe: trainTimeframe,
                            features: selectedFeatures,
                            tune: trainTune,
                            horizon: Number(trainHorizon) || 5,
                          });
                          startTrainPolling(res.task_id);
                        } catch (err) {
                          setError(
                            err instanceof Error ? err.message : "Failed to start training.",
                          );
                        } finally {
                          setTrainSubmitting(false);
                        }
                      }}
                    >
                      {trainSubmitting ? "Starting…" : "Train signal model"}
                    </Button>
                    {!trainSymbolId && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Select a symbol above to enable training.
                      </p>
                    )}
                    {selectedFeatures.length === 0 && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Select at least one feature in the config above to enable training.
                      </p>
                    )}
                  </div>

                  {/* Progress indicator */}
                  {trainTaskId && trainState && (
                    <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3 space-y-3">
                      <div className="flex items-center gap-3">
                        <svg
                          className="h-4 w-4 animate-spin text-blue-500 shrink-0"
                          viewBox="0 0 24 24"
                          fill="none"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          />
                        </svg>
                        <p className="text-sm text-blue-700 dark:text-blue-400">
                          {trainPhase ?? "Training in progress…"}
                        </p>
                        {trainProgressPct != null && (
                          <span className="ml-auto text-sm font-medium tabular-nums text-blue-700 dark:text-blue-400">
                            {trainProgressPct}%
                          </span>
                        )}
                      </div>
                      <Progress value={trainProgressPct ?? 0} className="h-2" />
                    </div>
                  )}

                  {/* Success */}
                  {trainResult && !trainResult.error && (
                    <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 space-y-1">
                      <p className="text-sm text-emerald-700 dark:text-emerald-400 font-medium">
                        Training complete!
                        {trainResult.accuracy != null && (
                          <span className="ml-2">
                            Accuracy:{" "}
                            <span className="font-semibold tabular-nums">
                              {(trainResult.accuracy * 100).toFixed(1)}%
                            </span>
                          </span>
                        )}
                        {trainResult.model_id != null && (
                          <span className="ml-2 text-xs opacity-70">(Model #{trainResult.model_id})</span>
                        )}
                      </p>
                      <p className="text-xs text-emerald-700/80 dark:text-emerald-400/80">
                        The new model has been auto-selected in the config above. Click &quot;Save as new
                        version&quot; to use it in backtests.
                      </p>
                    </div>
                  )}

                  {/* Failure */}
                  {trainResult?.error && (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
                      <p className="text-sm text-destructive">Training failed: {trainResult.error}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* ---- Version history card ---- */}
            <Card>
              <CardHeader>
                <CardTitle>Version history</CardTitle>
                <CardDescription>
                  All versions for this strategy. The active version will be used for backtests.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {strategy.versions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No versions yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="border-b border-border text-xs uppercase text-muted-foreground">
                        <tr>
                          <th className="py-2 text-left font-medium">Version</th>
                          <th className="py-2 text-left font-medium">Created</th>
                          <th className="py-2 text-left font-medium">Active</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...strategy.versions]
                          .sort((a, b) => b.version_number - a.version_number)
                          .map((v) => (
                            <tr key={v.id} className="border-b border-border last:border-0">
                              <td className="py-2 pr-4 align-middle">v{v.version_number}</td>
                              <td className="py-2 pr-4 align-middle text-muted-foreground">
                                {new Date(v.created_at).toLocaleString()}
                              </td>
                              <td className="py-2 pr-4 align-middle">
                                {v.is_active ? (
                                  <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
                                    Active
                                  </span>
                                ) : (
                                  <span className="text-xs text-muted-foreground">–</span>
                                )}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
