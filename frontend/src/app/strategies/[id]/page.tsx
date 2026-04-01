"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
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
  strategiesApi,
  type StrategyDetail,
} from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

type ConfigForm = {
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

  const [configForm, setConfigForm] = useState<ConfigForm | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  const [token, setToken] = useState<string | null>(null);
  const hasValidParams = !!token && !!strategyId && !Number.isNaN(strategyId);

  useEffect(() => {
    // Read token only on the client after mount to avoid SSR/client mismatches.
    Promise.resolve().then(() => {
      setToken(getToken());
    });
  }, []);

  useEffect(() => {
    if (!hasValidParams || !token) {
      return;
    }
    strategiesApi
      .get(token, strategyId)
      .then((data) => {
        setStrategy(data);
        setMetaName(data.name);
        setMetaDescription(data.description ?? "");
        const cfg = (data.versions.find((v) => v.is_active) ?? data.versions[0])
          ?.config as Record<string, unknown> | undefined;
        if (cfg) {
          setConfigForm({
            rsi_period: String(cfg.rsi_period ?? 14),
            rsi_buy_threshold: String(cfg.rsi_buy_threshold ?? 50),
            rsi_sell_threshold: String(cfg.rsi_sell_threshold ?? 50),
            ma_period: String(cfg.ma_period ?? 20),
            position_size_pct: String(Number(cfg.position_size_pct ?? 1.0) * 100),
            stop_loss_pct: String(cfg.stop_loss_pct ?? 2.0),
            take_profit_pct: String(cfg.take_profit_pct ?? 5.0),
            fee_rate: String(cfg.fee_rate ?? 0.001),
            slippage_rate: String(cfg.slippage_rate ?? 0.0005),
          });
        } else {
          setConfigForm({
            rsi_period: "14",
            rsi_buy_threshold: "50",
            rsi_sell_threshold: "50",
            ma_period: "20",
            position_size_pct: "100",
            stop_loss_pct: "2.0",
            take_profit_pct: "5.0",
            fee_rate: "0.001",
            slippage_rate: "0.0005",
          });
        }
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to load strategy.";
        setError(msg === "Not authenticated" ? "Please log in again." : msg);
      })
      .finally(() => setLoading(false));
  }, [strategyId, token, hasValidParams]);

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
      .then((updated) => {
        setStrategy(updated);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to update strategy.";
        setError(msg);
      })
      .finally(() => setSavingMeta(false));
  }

  function handleConfigChange(
    e: React.ChangeEvent<HTMLInputElement>,
  ) {
    const { name, value } = e.target;
    setConfigForm((prev) => (prev ? { ...prev, [name]: value } : prev));
  }

  function handleConfigSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!strategy || !token || !configForm) return;
    setSavingConfig(true);
    setError(null);
    const payload = {
      config: {
        rsi_period: Number(configForm.rsi_period) || undefined,
        rsi_buy_threshold: Number(configForm.rsi_buy_threshold) || undefined,
        rsi_sell_threshold: Number(configForm.rsi_sell_threshold) || undefined,
        ma_period: Number(configForm.ma_period) || undefined,
        position_size_pct:
          configForm.position_size_pct.trim() === ""
            ? undefined
            : Number(configForm.position_size_pct) / 100,
        stop_loss_pct: Number(configForm.stop_loss_pct) || undefined,
        take_profit_pct: Number(configForm.take_profit_pct) || undefined,
        fee_rate: Number(configForm.fee_rate) || undefined,
        slippage_rate: Number(configForm.slippage_rate) || undefined,
      },
    };
    strategiesApi
      .createVersion(token, strategy.id, payload)
      .then((updated) => {
        setStrategy(updated);
        const cfg = (updated.versions.find((v) => v.is_active) ?? updated.versions[0])
          ?.config as Record<string, unknown> | undefined;
        if (cfg) {
          setConfigForm({
            rsi_period: String(cfg.rsi_period ?? 14),
            rsi_buy_threshold: String(cfg.rsi_buy_threshold ?? 30),
            rsi_sell_threshold: String(cfg.rsi_sell_threshold ?? 70),
            ma_period: String(cfg.ma_period ?? 20),
            position_size_pct: String(Number(cfg.position_size_pct ?? 1.0) * 100),
            stop_loss_pct: String(cfg.stop_loss_pct ?? 2.0),
            take_profit_pct: String(cfg.take_profit_pct ?? 5.0),
            fee_rate: String(cfg.fee_rate ?? 0.001),
            slippage_rate: String(cfg.slippage_rate ?? 0.0005),
          });
        }
        router.refresh();
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to create new version.";
        setError(msg);
      })
      .finally(() => setSavingConfig(false));
  }

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
          <p className="text-sm text-destructive">
            Missing strategy id or not authenticated.
          </p>
        )}
        {error && hasValidParams && (
          <p className="text-sm text-destructive">
            {error}
          </p>
        )}
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
                    <p className="text-sm text-muted-foreground uppercase">
                      {strategy.strategy_type}
                    </p>
                  </div>
                  <div className="flex items-center justify-end gap-3 pt-2">
                    <Button type="submit" size="sm" disabled={savingMeta || !token}>
                      {savingMeta ? "Saving…" : "Save changes"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Active version config</CardTitle>
                <CardDescription>
                  Adjust parameters and save as a new version. The latest active version will be
                  used for backtests.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {strategy.strategy_type !== "rsi_ma" ? (
                  <p className="text-sm text-muted-foreground">
                    Editing is currently only supported for RSI + MA strategies.
                  </p>
                ) : !configForm ? (
                  <p className="text-sm text-muted-foreground">Loading config…</p>
                ) : (
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
                            value={configForm.rsi_period}
                            onChange={handleConfigChange}
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
                            value={configForm.rsi_buy_threshold}
                            onChange={handleConfigChange}
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
                            value={configForm.rsi_sell_threshold}
                            onChange={handleConfigChange}
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
                          value={configForm.ma_period}
                          onChange={handleConfigChange}
                        />
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h2 className="text-sm font-semibold text-muted-foreground">
                        Position &amp; risk
                      </h2>
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
                            value={configForm.position_size_pct}
                            onChange={handleConfigChange}
                          />
                          <p className="text-xs text-muted-foreground">
                            Enter `100` to use the full account balance per trade.
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
                            value={configForm.stop_loss_pct}
                            onChange={handleConfigChange}
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
                            value={configForm.take_profit_pct}
                            onChange={handleConfigChange}
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
                            value={configForm.fee_rate}
                            onChange={handleConfigChange}
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
                            value={configForm.slippage_rate}
                            onChange={handleConfigChange}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 pt-2">
                      <Button
                        type="submit"
                        size="sm"
                        disabled={savingConfig || !token}
                      >
                        {savingConfig ? "Saving…" : "Save as new version"}
                      </Button>
                    </div>
                  </form>
                )}
              </CardContent>
            </Card>

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
                              <td className="py-2 pr-4 align-middle">
                                v{v.version_number}
                              </td>
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

