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
  // ML Signal
  const [mlForm, setMlForm] = useState<MlSignalConfigForm | null>(null);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>(DEFAULT_ML_FEATURES);
  const [featureCatalog, setFeatureCatalog] = useState<string[]>([]);
  const [models, setModels] = useState<ModelInfoOut[]>([]);

  const [savingConfig, setSavingConfig] = useState(false);

  // Signal model training state
  const [symbols, setSymbols] = useState<Symbol[]>([]);
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
  const trainPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const hasValidParams = !!token && !!strategyId && !Number.isNaN(strategyId);

  useEffect(() => {
    Promise.resolve().then(() => setToken(getToken()));
  }, []);

  // Load symbols for training
  useEffect(() => {
    symbolsApi.list().then(setSymbols).catch(() => {});
  }, []);

  const stopTrainPolling = useCallback(() => {
    if (trainPollRef.current) {
      clearInterval(trainPollRef.current);
      trainPollRef.current = null;
    }
  }, []);

  const startTrainPolling = useCallback(
    (taskId: string) => {
      stopTrainPolling();
      setTrainTaskId(taskId);
      setTrainState("PENDING");
      setTrainProgressPct(0);
      setTrainPhase("Queued");
      setTrainResult(null);

      trainPollRef.current = setInterval(async () => {
        const t = getToken();
        if (!t) return;
        try {
          const s = await strategiesApi.getSignalTrainStatus(t, taskId);
          setTrainState(s.state);
          if (s.progress_pct != null) setTrainProgressPct(s.progress_pct);
          if (s.phase != null) setTrainPhase(s.phase);

          if (s.state === "SUCCESS" && !s.error) {
            stopTrainPolling();
            setTrainProgressPct(100);
            setTrainPhase("Complete");
            setTrainResult({ accuracy: s.accuracy, model_id: s.model_id, error: null });
            setTrainTaskId(null);
            if (t) {
              regimesApi.listModels(t).then((r) => setModels(r.models)).catch(() => {});
            }
          } else if (s.state === "FAILURE" || s.error) {
            stopTrainPolling();
            setTrainProgressPct(null);
            setTrainPhase(null);
            setTrainResult({ accuracy: null, model_id: null, error: s.error || "Training failed" });
            setTrainTaskId(null);
          }
        } catch {
          // transient error, keep polling
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
    regimesApi.listModels(token).then((r) => setModels(r.models)).catch(() => {});
  }, [token, strategy]);

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
        setError("Please select a trained ML model.");
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
                    <Input id="meta-name" value={metaName} onChange={(e) => setMetaName(e.target.value)} required />
                  </div>
                  <div className="space-y-1.5 max-w-md">
                    <Label htmlFor="meta-description">Description</Label>
                    <Input id="meta-description" value={metaDescription} onChange={(e) => setMetaDescription(e.target.value)} placeholder="Optional description" />
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
                          <Input id="rsi_period" name="rsi_period" type="number" min={2} max={100} value={rsiForm.rsi_period} onChange={handleRsiChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="rsi_buy_threshold">Buy threshold</Label>
                          <Input id="rsi_buy_threshold" name="rsi_buy_threshold" type="number" min={0} max={100} value={rsiForm.rsi_buy_threshold} onChange={handleRsiChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="rsi_sell_threshold">Sell threshold</Label>
                          <Input id="rsi_sell_threshold" name="rsi_sell_threshold" type="number" min={0} max={100} value={rsiForm.rsi_sell_threshold} onChange={handleRsiChange} />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Trend filter</h2>
                      <div className="space-y-1.5 max-w-xs">
                        <Label htmlFor="ma_period">MA period</Label>
                        <Input id="ma_period" name="ma_period" type="number" min={1} max={500} value={rsiForm.ma_period} onChange={handleRsiChange} />
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Position &amp; risk</h2>
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label htmlFor="position_size_pct">Position size (%)</Label>
                          <Input id="position_size_pct" name="position_size_pct" type="number" min={0.01} max={100} step={0.01} value={rsiForm.position_size_pct} onChange={handleRsiChange} />
                          <p className="text-xs text-muted-foreground">Enter `100` to use the full account balance per trade.</p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="stop_loss_pct">Stop loss (%)</Label>
                          <Input id="stop_loss_pct" name="stop_loss_pct" type="number" min={0} max={100} step={0.1} value={rsiForm.stop_loss_pct} onChange={handleRsiChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="take_profit_pct">Take profit (%)</Label>
                          <Input id="take_profit_pct" name="take_profit_pct" type="number" min={0} max={100} step={0.1} value={rsiForm.take_profit_pct} onChange={handleRsiChange} />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="fee_rate">Fee rate (fraction)</Label>
                          <Input id="fee_rate" name="fee_rate" type="number" min={0} max={1} step={0.0001} value={rsiForm.fee_rate} onChange={handleRsiChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="slippage_rate">Slippage rate (fraction)</Label>
                          <Input id="slippage_rate" name="slippage_rate" type="number" min={0} max={1} step={0.0001} value={rsiForm.slippage_rate} onChange={handleRsiChange} />
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
                    {/* Model picker */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Model</h2>
                      <div className="space-y-1.5 max-w-md">
                        <Label htmlFor="model_id">Trained model</Label>
                        <select
                          id="model_id"
                          name="model_id"
                          value={mlForm.model_id}
                          onChange={handleMlChange}
                          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <option value="">Select a model…</option>
                          {models.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name} — acc{" "}
                              {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "n/a"}{" "}
                              ({m.timeframe ?? "?"})
                            </option>
                          ))}
                        </select>
                        {models.length === 0 && (
                          <p className="text-xs text-muted-foreground">
                            No trained models found. Train one from the{" "}
                            <Link href="/market-data" className="underline text-primary">Market data</Link> page first.
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Feature selection */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Features</h2>
                      <p className="text-xs text-muted-foreground">
                        Select the features your model was trained on. These must match the training feature set.
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
                          <Input id="long_threshold" name="long_threshold" type="number" min={0} max={1} step={0.01} value={mlForm.long_threshold} onChange={handleMlChange} />
                          <p className="text-xs text-muted-foreground">Enter long when P(up) &ge; this value</p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="exit_threshold">Exit threshold</Label>
                          <Input id="exit_threshold" name="exit_threshold" type="number" min={0} max={1} step={0.01} value={mlForm.exit_threshold} onChange={handleMlChange} />
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
                          <Input id="ml_position_size_pct" name="position_size_pct" type="number" min={0.01} max={100} step={0.01} value={mlForm.position_size_pct} onChange={handleMlChange} />
                          <p className="text-xs text-muted-foreground">Enter `100` to use the full account balance per trade.</p>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_stop_loss_pct">Stop loss (%)</Label>
                          <Input id="ml_stop_loss_pct" name="stop_loss_pct" type="number" min={0} max={100} step={0.1} value={mlForm.stop_loss_pct} onChange={handleMlChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_take_profit_pct">Take profit (%)</Label>
                          <Input id="ml_take_profit_pct" name="take_profit_pct" type="number" min={0} max={100} step={0.1} value={mlForm.take_profit_pct} onChange={handleMlChange} />
                        </div>
                      </div>
                    </div>

                    {/* Execution */}
                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_fee_rate">Fee rate (fraction)</Label>
                          <Input id="ml_fee_rate" name="fee_rate" type="number" min={0} max={1} step={0.0001} value={mlForm.fee_rate} onChange={handleMlChange} />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="ml_slippage_rate">Slippage rate (fraction)</Label>
                          <Input id="ml_slippage_rate" name="slippage_rate" type="number" min={0} max={1} step={0.0001} value={mlForm.slippage_rate} onChange={handleMlChange} />
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
                {strategy.strategy_type !== "rsi_ma" &&
                  strategy.strategy_type !== "ml_signal" && (
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
                    Train a new ML signal model for this strategy&apos;s symbol and timeframe.
                    The model predicts probability of upward price movement.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {(() => {
                    const cfg = (strategy.versions.find((v) => v.is_active) ?? strategy.versions[0])
                      ?.config as Record<string, unknown> | undefined;
                    const cfgModelId = cfg?.model_id as number | undefined;
                    const cfgFeatures = (cfg?.features ?? selectedFeatures) as string[];
                    const linkedModel = models.find((m) => m.id === cfgModelId);
                    const symbolName = symbols.find((s) => s.id === linkedModel?.symbol_id)?.symbol;

                    return (
                      <>
                        {linkedModel && (
                          <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm space-y-1">
                            <p>
                              <span className="text-muted-foreground">Linked model:</span>{" "}
                              <span className="font-medium">#{linkedModel.id} {linkedModel.name}</span>
                              {linkedModel.accuracy != null && (
                                <span className="ml-2 text-muted-foreground">
                                  acc {(linkedModel.accuracy * 100).toFixed(1)}%
                                </span>
                              )}
                            </p>
                            <p className="text-muted-foreground">
                              {symbolName ?? `Symbol #${linkedModel.symbol_id}`} · {linkedModel.timeframe}
                            </p>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-3">
                          <div className="space-y-1.5">
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
                          <label className="flex items-center gap-2 text-sm cursor-pointer mt-6">
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

                        <div className="flex flex-wrap gap-2">
                          <Button
                            disabled={trainSubmitting || !!trainTaskId}
                            onClick={async () => {
                              const t = getToken();
                              if (!t || !linkedModel) return;
                              setTrainSubmitting(true);
                              setError(null);
                              setTrainResult(null);
                              try {
                                const res = await strategiesApi.trainSignalModel(t, {
                                  symbol_id: linkedModel.symbol_id!,
                                  timeframe: linkedModel.timeframe ?? "1h",
                                  features: cfgFeatures,
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
                          {!linkedModel && (
                            <p className="text-sm text-muted-foreground self-center">
                              Select a model in the config above first, or train a regime model from{" "}
                              <Link href="/market-data" className="underline text-primary">Market data</Link>.
                            </p>
                          )}
                        </div>

                        {trainTaskId && trainState && (
                          <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3 space-y-3">
                            <div className="flex items-center gap-3">
                              <svg className="h-4 w-4 animate-spin text-blue-500 shrink-0" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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

                        {trainResult && !trainResult.error && (
                          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                            <p className="text-sm text-emerald-700 dark:text-emerald-400">
                              Training complete!
                              {trainResult.accuracy != null && (
                                <span className="ml-2">
                                  Accuracy: <span className="font-semibold tabular-nums">{(trainResult.accuracy * 100).toFixed(1)}%</span>
                                </span>
                              )}
                              {trainResult.model_id != null && (
                                <span className="ml-2 text-xs opacity-70">(Model #{trainResult.model_id})</span>
                              )}
                            </p>
                          </div>
                        )}

                        {trainResult?.error && (
                          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
                            <p className="text-sm text-destructive">Training failed: {trainResult.error}</p>
                          </div>
                        )}
                      </>
                    );
                  })()}
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
