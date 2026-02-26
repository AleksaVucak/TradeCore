"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { marketDataApi, symbolsApi, type Symbol } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

function toISO(date: Date) {
  return date.toISOString().slice(0, 19) + "Z";
}

export default function MarketDataPage() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<string | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);

  async function handleIngestLast30Days() {
    const token = getToken();
    if (!token) {
      setError("Please log in to trigger ingestion.");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const symbols = await symbolsApi.list();
      const btc = symbols.find((s: Symbol) => s.symbol === "BTCUSD");
      const eth = symbols.find((s: Symbol) => s.symbol === "ETHUSD");
      if (!btc || !eth) {
        setError("BTCUSD or ETHUSD not found. Run seed first.");
        return;
      }
      const end = new Date();
      const start = new Date(end);
      start.setDate(start.getDate() - 30);
      const startStr = toISO(start);
      const endStr = toISO(end);
      await marketDataApi.ingest(
        token,
        { symbol_id: btc.id, timeframe: "1h", start_date: startStr, end_date: endStr }
      );
      await marketDataApi.ingest(
        token,
        { symbol_id: eth.id, timeframe: "1h", start_date: startStr, end_date: endStr }
      );
      setMessage("Ingestion started for BTCUSD and ETHUSD (last 30 days, 1h).");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify() {
    const token = getToken();
    if (!token) {
      setVerifyResult("Please log in to verify.");
      return;
    }
    setVerifyLoading(true);
    setVerifyResult(null);
    try {
      const symbols = await symbolsApi.list();
      const btc = symbols.find((s: Symbol) => s.symbol === "BTCUSD");
      const eth = symbols.find((s: Symbol) => s.symbol === "ETHUSD");
      if (!btc || !eth) {
        setVerifyResult("BTCUSD or ETHUSD not found.");
        return;
      }
      const end = new Date();
      const start = new Date(end);
      start.setDate(start.getDate() - 7);
      const startStr = toISO(start);
      const endStr = toISO(end);
      const [btcCandles, ethCandles] = await Promise.all([
        marketDataApi.candles(token, { symbol_id: btc.id, timeframe: "1h", start: startStr, end: endStr }),
        marketDataApi.candles(token, { symbol_id: eth.id, timeframe: "1h", start: startStr, end: endStr }),
      ]);
      setVerifyResult(
        `BTCUSD 1h: ${btcCandles.length} candles. ETHUSD 1h: ${ethCandles.length} candles (last 7 days).`
      );
    } catch (err) {
      setVerifyResult(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setVerifyLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">Market data</h1>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Load historical candles</CardTitle>
            <CardDescription>
              Fetch OHLCV from Binance and store in the database (idempotent). Requires login.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={handleIngestLast30Days}
              disabled={loading}
            >
              {loading ? "Starting…" : "Load last 30 days (BTC & ETH, 1h)"}
            </Button>
            {message && <p className="text-sm text-muted-foreground">{message}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Verify stored data</CardTitle>
            <CardDescription>
              After ingestion runs in the background (give it 1–2 minutes), check that candles are in the database.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" onClick={handleVerify} disabled={verifyLoading}>
              {verifyLoading ? "Checking…" : "Check candle counts (last 7 days)"}
            </Button>
            {verifyResult && <p className="text-sm text-muted-foreground">{verifyResult}</p>}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
