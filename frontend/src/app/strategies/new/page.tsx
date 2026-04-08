"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
  type ModelInfoOut,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Strategy type definition
// ---------------------------------------------------------------------------
type StrategyTypeOption = "rsi_ma" | "ml_signal";

const STRATEGY_TYPE_LABELS: Record<StrategyTypeOption, string> = {
  rsi_ma: "RSI + Moving Average",
  ml_signal: "ML Signal",
};

// ---------------------------------------------------------------------------
// RSI+MA form state
// ---------------------------------------------------------------------------
type RsiMaForm = {
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

const initialRsiMaForm: RsiMaForm = {
  rsi_period: "14",
  rsi_buy_threshold: "30",
  rsi_sell_threshold: "70",
  ma_period: "20",
  position_size_pct: "100",
  stop_loss_pct: "2.0",
  take_profit_pct: "5.0",
  fee_rate: "0.001",
  slippage_rate: "0.0005",
};

// ---------------------------------------------------------------------------
// ML Signal form state
// ---------------------------------------------------------------------------
type MlSignalForm = {
  model_id: string;
  long_threshold: string;
  exit_threshold: string;
  position_size_pct: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  fee_rate: string;
  slippage_rate: string;
};

const initialMlSignalForm: MlSignalForm = {
  model_id: "",
  long_threshold: "0.55",
  exit_threshold: "0.45",
  position_size_pct: "100",
  stop_loss_pct: "3.0",
  take_profit_pct: "6.0",
  fee_rate: "0.001",
  slippage_rate: "0.0005",
};

const DEFAULT_ML_FEATURES = [
  "rsi_14",
  "sma_20",
  "macd",
  "bbands_width",
  "atr_14",
  "log_return_1",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function NewStrategyPage() {
  const router = useRouter();
  const [strategyType, setStrategyType] = useState<StrategyTypeOption>("rsi_ma");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rsiMa, setRsiMa] = useState<RsiMaForm>(initialRsiMaForm);
  const [mlSignal, setMlSignal] = useState<MlSignalForm>(initialMlSignalForm);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>(DEFAULT_ML_FEATURES);

  const [featureCatalog, setFeatureCatalog] = useState<string[]>([]);
  const [models, setModels] = useState<ModelInfoOut[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    Promise.resolve().then(() => setToken(getToken()));
  }, []);

  // Fetch ML feature catalog + trained models when the ML tab is active
  useEffect(() => {
    if (strategyType !== "ml_signal" || !token) return;
    strategiesApi.mlFeatures(token).then(setFeatureCatalog).catch(() => {});
    regimesApi.listModels(token).then((r) => setModels(r.models)).catch(() => {});
  }, [strategyType, token]);

  function handleRsiChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name: field, value } = e.target;
    setRsiMa((prev) => ({ ...prev, [field]: value }));
  }

  function handleMlChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name: field, value } = e.target;
    setMlSignal((prev) => ({ ...prev, [field]: value }));
  }

  function toggleFeature(feat: string) {
    setSelectedFeatures((prev) =>
      prev.includes(feat) ? prev.filter((f) => f !== feat) : [...prev, feat],
    );
  }

  function buildPayload(): {
    name: string;
    description: string | null;
    strategy_type: string;
    config: Record<string, unknown>;
  } | null {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Name is required.");
      return null;
    }

    if (strategyType === "rsi_ma") {
      return {
        name: trimmedName,
        description: description.trim() || null,
        strategy_type: "rsi_ma",
        config: {
          rsi_period: Number(rsiMa.rsi_period) || undefined,
          rsi_buy_threshold: Number(rsiMa.rsi_buy_threshold) || undefined,
          rsi_sell_threshold: Number(rsiMa.rsi_sell_threshold) || undefined,
          ma_period: Number(rsiMa.ma_period) || undefined,
          position_size_pct:
            rsiMa.position_size_pct.trim() === ""
              ? undefined
              : Number(rsiMa.position_size_pct) / 100,
          stop_loss_pct: Number(rsiMa.stop_loss_pct) || undefined,
          take_profit_pct: Number(rsiMa.take_profit_pct) || undefined,
          fee_rate: Number(rsiMa.fee_rate) || undefined,
          slippage_rate: Number(rsiMa.slippage_rate) || undefined,
        },
      };
    }

    // ml_signal
    if (!mlSignal.model_id) {
      setError("Please select a trained ML model.");
      return null;
    }
    if (selectedFeatures.length === 0) {
      setError("Please select at least one feature.");
      return null;
    }

    return {
      name: trimmedName,
      description: description.trim() || null,
      strategy_type: "ml_signal",
      config: {
        model_id: Number(mlSignal.model_id),
        features: selectedFeatures,
        long_threshold: Number(mlSignal.long_threshold),
        exit_threshold: Number(mlSignal.exit_threshold),
        position_size_pct:
          mlSignal.position_size_pct.trim() === ""
            ? undefined
            : Number(mlSignal.position_size_pct) / 100,
        stop_loss_pct: Number(mlSignal.stop_loss_pct) || undefined,
        take_profit_pct: Number(mlSignal.take_profit_pct) || undefined,
        fee_rate: Number(mlSignal.fee_rate) || undefined,
        slippage_rate: Number(mlSignal.slippage_rate) || undefined,
      },
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("Please log in to create a strategy.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = buildPayload();
      if (!payload) {
        setSubmitting(false);
        return;
      }
      await strategiesApi.create(token, payload);
      router.push("/strategies");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create strategy. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          <Link href="/strategies" className="text-muted-foreground hover:text-foreground text-sm">
            ← Back to strategies
          </Link>
          <h1 className="text-xl font-semibold tracking-tight mt-1">New strategy</h1>
        </div>
      </header>
      <main className="container mx-auto max-w-3xl px-6 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Create strategy</CardTitle>
            <CardDescription>
              Choose a strategy type and configure its parameters. You&apos;ll use this in backtests
              later.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!token && (
              <p className="mb-4 text-sm text-destructive">Please log in to create a strategy.</p>
            )}
            {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
            <form className="space-y-6" onSubmit={handleSubmit}>
              {/* ---------- Name & description ---------- */}
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My strategy"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="description">Description</Label>
                  <Input
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optional description"
                  />
                </div>
              </div>

              {/* ---------- Strategy type picker ---------- */}
              <div className="space-y-1.5">
                <Label>Strategy type</Label>
                <div className="flex gap-2">
                  {(Object.keys(STRATEGY_TYPE_LABELS) as StrategyTypeOption[]).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setStrategyType(t)}
                      className={`rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
                        strategyType === t
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input bg-background hover:bg-accent hover:text-accent-foreground"
                      }`}
                    >
                      {STRATEGY_TYPE_LABELS[t]}
                    </button>
                  ))}
                </div>
              </div>

              {/* ---------- RSI + MA config ---------- */}
              {strategyType === "rsi_ma" && (
                <>
                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">RSI</h2>
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="rsi_period">RSI period</Label>
                        <Input id="rsi_period" name="rsi_period" type="number" min={2} max={100} value={rsiMa.rsi_period} onChange={handleRsiChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="rsi_buy_threshold">Buy threshold</Label>
                        <Input id="rsi_buy_threshold" name="rsi_buy_threshold" type="number" min={0} max={100} value={rsiMa.rsi_buy_threshold} onChange={handleRsiChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="rsi_sell_threshold">Sell threshold</Label>
                        <Input id="rsi_sell_threshold" name="rsi_sell_threshold" type="number" min={0} max={100} value={rsiMa.rsi_sell_threshold} onChange={handleRsiChange} />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Trend filter</h2>
                    <div className="space-y-1.5 max-w-xs">
                      <Label htmlFor="ma_period">MA period</Label>
                      <Input id="ma_period" name="ma_period" type="number" min={1} max={500} value={rsiMa.ma_period} onChange={handleRsiChange} />
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Position &amp; risk</h2>
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="position_size_pct">Position size (%)</Label>
                        <Input id="position_size_pct" name="position_size_pct" type="number" min={0.01} max={100} step={0.01} value={rsiMa.position_size_pct} onChange={handleRsiChange} />
                        <p className="text-xs text-muted-foreground">Enter `100` to use the full account balance per trade.</p>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="stop_loss_pct">Stop loss (%)</Label>
                        <Input id="stop_loss_pct" name="stop_loss_pct" type="number" min={0} max={100} step={0.1} value={rsiMa.stop_loss_pct} onChange={handleRsiChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="take_profit_pct">Take profit (%)</Label>
                        <Input id="take_profit_pct" name="take_profit_pct" type="number" min={0} max={100} step={0.1} value={rsiMa.take_profit_pct} onChange={handleRsiChange} />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="fee_rate">Fee rate (fraction)</Label>
                        <Input id="fee_rate" name="fee_rate" type="number" min={0} max={1} step={0.0001} value={rsiMa.fee_rate} onChange={handleRsiChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="slippage_rate">Slippage rate (fraction)</Label>
                        <Input id="slippage_rate" name="slippage_rate" type="number" min={0} max={1} step={0.0001} value={rsiMa.slippage_rate} onChange={handleRsiChange} />
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* ---------- ML Signal config ---------- */}
              {strategyType === "ml_signal" && (
                <>
                  {/* Model picker */}
                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Model</h2>
                    <div className="space-y-1.5 max-w-md">
                      <Label htmlFor="model_id">Trained model</Label>
                      <select
                        id="model_id"
                        name="model_id"
                        value={mlSignal.model_id}
                        onChange={handleMlChange}
                        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      >
                        <option value="">Select a model…</option>
                        {models.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} — acc {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "n/a"}{" "}
                            ({m.timeframe ?? "?"})
                          </option>
                        ))}
                      </select>
                      {models.length === 0 && (
                        <p className="text-xs text-muted-foreground">
                          No trained models found. Train one from the{" "}
                          <Link href="/market-data" className="underline text-primary">
                            Market data
                          </Link>{" "}
                          page first.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Feature selection */}
                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Features</h2>
                    <p className="text-xs text-muted-foreground">
                      Select the features your model was trained on. These must match the training
                      feature set.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {(featureCatalog.length > 0 ? featureCatalog : DEFAULT_ML_FEATURES).map(
                        (feat) => {
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
                        },
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {selectedFeatures.length} feature{selectedFeatures.length !== 1 ? "s" : ""}{" "}
                      selected
                    </p>
                  </div>

                  {/* Thresholds */}
                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Signal thresholds</h2>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="long_threshold">Long threshold</Label>
                        <Input id="long_threshold" name="long_threshold" type="number" min={0} max={1} step={0.01} value={mlSignal.long_threshold} onChange={handleMlChange} />
                        <p className="text-xs text-muted-foreground">Enter long when P(up) &ge; this value</p>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="exit_threshold">Exit threshold</Label>
                        <Input id="exit_threshold" name="exit_threshold" type="number" min={0} max={1} step={0.01} value={mlSignal.exit_threshold} onChange={handleMlChange} />
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
                        <Input id="ml_position_size_pct" name="position_size_pct" type="number" min={0.01} max={100} step={0.01} value={mlSignal.position_size_pct} onChange={handleMlChange} />
                        <p className="text-xs text-muted-foreground">Enter `100` to use the full account balance per trade.</p>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="ml_stop_loss_pct">Stop loss (%)</Label>
                        <Input id="ml_stop_loss_pct" name="stop_loss_pct" type="number" min={0} max={100} step={0.1} value={mlSignal.stop_loss_pct} onChange={handleMlChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="ml_take_profit_pct">Take profit (%)</Label>
                        <Input id="ml_take_profit_pct" name="take_profit_pct" type="number" min={0} max={100} step={0.1} value={mlSignal.take_profit_pct} onChange={handleMlChange} />
                      </div>
                    </div>
                  </div>

                  {/* Execution */}
                  <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-muted-foreground">Execution</h2>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="ml_fee_rate">Fee rate (fraction)</Label>
                        <Input id="ml_fee_rate" name="fee_rate" type="number" min={0} max={1} step={0.0001} value={mlSignal.fee_rate} onChange={handleMlChange} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="ml_slippage_rate">Slippage rate (fraction)</Label>
                        <Input id="ml_slippage_rate" name="slippage_rate" type="number" min={0} max={1} step={0.0001} value={mlSignal.slippage_rate} onChange={handleMlChange} />
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* ---------- Actions ---------- */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <Button type="button" variant="outline" onClick={() => router.push("/strategies")} disabled={submitting}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting || !token}>
                  {submitting ? "Creating…" : "Create strategy"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
