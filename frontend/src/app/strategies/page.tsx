"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { strategiesApi, type StrategyListItem } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setError("Please log in to view strategies.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    strategiesApi
      .list(token)
      .then((items) => {
        setStrategies(items);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : "Failed to load strategies.";
        setError(msg === "Not authenticated" ? "Please log in again." : msg);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">Strategies</h1>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">
              Your saved trading strategies. New strategy creation and editing will be added next.
            </p>
          </div>
          <Link
            href="#"
            className="text-sm font-medium text-muted-foreground cursor-not-allowed"
            aria-disabled
          >
            New strategy (coming soon)
          </Link>
        </div>

        {error && (
          <p className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Strategies</CardTitle>
            <CardDescription>
              {loading
                ? "Loading your strategies…"
                : strategies.length === 0
                ? "No strategies yet. You’ll be able to create one from here in the next phase."
                : "List of your strategies."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : strategies.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No strategies found. Once creation is implemented, you’ll see them here.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-border text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="py-2 text-left font-medium">Name</th>
                      <th className="py-2 text-left font-medium">Type</th>
                      <th className="py-2 text-left font-medium">Created</th>
                      <th className="py-2 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategies.map((s) => (
                      <tr
                        key={s.id}
                        className="border-b border-border last:border-0 hover:bg-accent/40"
                      >
                        <td className="py-2 pr-4 align-middle">
                          <span className="font-medium">{s.name}</span>
                        </td>
                        <td className="py-2 pr-4 align-middle">
                          <span className="rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wide">
                            {s.strategy_type}
                          </span>
                        </td>
                        <td className="py-2 pr-4 align-middle text-muted-foreground">
                          {new Date(s.created_at).toLocaleString()}
                        </td>
                        <td className="py-2 pl-4 align-middle text-right">
                          <Link
                            href={`/strategies/${s.id}`}
                            className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                          >
                            View details
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
