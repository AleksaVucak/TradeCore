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
import { strategiesApi } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

type FormState = {
  name: string;
  description: string;
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

const initialForm: FormState = {
  name: "",
  description: "",
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

export default function NewStrategyPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    Promise.resolve().then(() => {
      setToken(getToken());
    });
  }, []);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement>,
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
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
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        strategy_type: "rsi_ma",
        config: {
          // Let the backend schema handle defaults/validation; we coerce to numbers where sensible.
          rsi_period: Number(form.rsi_period) || undefined,
          rsi_buy_threshold: Number(form.rsi_buy_threshold) || undefined,
          rsi_sell_threshold: Number(form.rsi_sell_threshold) || undefined,
          ma_period: Number(form.ma_period) || undefined,
          position_size_pct:
            form.position_size_pct.trim() === ""
              ? undefined
              : Number(form.position_size_pct) / 100,
          stop_loss_pct: Number(form.stop_loss_pct) || undefined,
          take_profit_pct: Number(form.take_profit_pct) || undefined,
          fee_rate: Number(form.fee_rate) || undefined,
          slippage_rate: Number(form.slippage_rate) || undefined,
        },
      };
      if (!payload.name) {
        setError("Name is required.");
        setSubmitting(false);
        return;
      }
      await strategiesApi.create(token, payload);
      // After creating, go back to strategies list; users can open the detail page from there.
      router.push("/strategies");
      // Alternatively, we could navigate directly to `/strategies/${created.id}` instead.
      router.refresh();
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to create strategy. Please try again.";
      setError(msg);
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
            <CardTitle>Create RSI + MA strategy</CardTitle>
            <CardDescription>
              Configure an RSI + moving-average strategy. You&apos;ll use this in backtests later.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!token && (
              <p className="mb-4 text-sm text-destructive">
                Please log in to create a strategy.
              </p>
            )}
            {error && (
              <p className="mb-4 text-sm text-destructive">
                {error}
              </p>
            )}
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    name="name"
                    value={form.name}
                    onChange={handleChange}
                    placeholder="My RSI MA strategy"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="description">Description</Label>
                  <Input
                    id="description"
                    name="description"
                    value={form.description}
                    onChange={handleChange}
                    placeholder="Optional description"
                  />
                </div>
              </div>

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
                      value={form.rsi_period}
                      onChange={handleChange}
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
                      value={form.rsi_buy_threshold}
                      onChange={handleChange}
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
                      value={form.rsi_sell_threshold}
                      onChange={handleChange}
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
                    value={form.ma_period}
                    onChange={handleChange}
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
                      value={form.position_size_pct}
                      onChange={handleChange}
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
                      value={form.stop_loss_pct}
                      onChange={handleChange}
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
                      value={form.take_profit_pct}
                      onChange={handleChange}
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
                      value={form.fee_rate}
                      onChange={handleChange}
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
                      value={form.slippage_rate}
                      onChange={handleChange}
                    />
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => router.push("/strategies")}
                  disabled={submitting}
                >
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

