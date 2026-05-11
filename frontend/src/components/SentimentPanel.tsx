"use client";

/**
 * Phase 17.4 — reusable sentiment display component.
 *
 * Shows aggregate sentiment statistics and the most recent scored headlines
 * for a single symbol, fed by the Phase 17.2 sentiment API. Used on the
 * market-data screen (current symbol context) and run detail screen
 * (run date range).
 */

import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  sentimentApi,
  type SentimentAggregateOut,
  type SentimentScoreOut,
} from "@/lib/api/endpoints";

type SentimentPanelProps = {
  /** Token used for all sentiment API calls. */
  token: string | null;
  /** Symbol string used in URL (e.g. "BTCUSD"). */
  symbol: string;
  /** Symbol primary key — only needed if `showRefresh` is true. */
  symbolId?: number | null;
  /** Optional ISO-8601 lower bound. Both aggregate and list use it. */
  start?: string | null;
  /** Optional ISO-8601 upper bound. Both aggregate and list use it. */
  end?: string | null;
  /** How many recent rows to fetch. Default 20, capped server-side at 500. */
  limit?: number;
  /** Optional title override (defaults to "News sentiment"). */
  title?: string;
  /** Optional description override. */
  description?: string;
  /** Show the "Refresh news" button (requires `symbolId`). */
  showRefresh?: boolean;
  /** When true, fetch aggregate stats. Default true. */
  showAggregate?: boolean;
  /** When true, fetch + render recent score list. Default true. */
  showList?: boolean;
};

const LABEL_COLOR: Record<string, string> = {
  positive: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  negative: "bg-destructive/15 text-destructive",
  neutral: "bg-muted text-muted-foreground",
};

function labelClass(label: string): string {
  return LABEL_COLOR[label.toLowerCase()] ?? LABEL_COLOR.neutral;
}

function formatPublished(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function formatScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "—";
  const sign = score > 0 ? "+" : "";
  return `${sign}${score.toFixed(3)}`;
}

export function SentimentPanel({
  token,
  symbol,
  symbolId = null,
  start = null,
  end = null,
  limit = 20,
  title = "News sentiment",
  description,
  showRefresh = false,
  showAggregate = true,
  showList = true,
}: SentimentPanelProps) {
  const [aggregate, setAggregate] = useState<SentimentAggregateOut | null>(null);
  const [scores, setScores] = useState<SentimentScoreOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token || !symbol) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    const requests: Promise<unknown>[] = [];
    if (showAggregate) {
      requests.push(
        sentimentApi.getAggregate(token, symbol, {
          start: start ?? undefined,
          end: end ?? undefined,
        }),
      );
    } else {
      requests.push(Promise.resolve(null));
    }
    if (showList) {
      requests.push(
        sentimentApi.getForSymbol(token, symbol, {
          limit,
          start: start ?? undefined,
          end: end ?? undefined,
        }),
      );
    } else {
      requests.push(Promise.resolve(null));
    }

    const [aggResult, listResult] = await Promise.allSettled(requests);

    if (aggResult.status === "fulfilled") {
      setAggregate((aggResult.value as SentimentAggregateOut | null) ?? null);
    } else if (showAggregate) {
      // Don't blow up the whole panel if aggregate fails but list succeeds.
      setAggregate(null);
    }

    if (listResult.status === "fulfilled") {
      const data = listResult.value as { scores: SentimentScoreOut[] } | null;
      setScores(data?.scores ?? []);
    } else if (showList) {
      setScores([]);
    }

    const aggFailed =
      showAggregate && aggResult.status === "rejected";
    const listFailed = showList && listResult.status === "rejected";
    if (aggFailed && listFailed) {
      const reason =
        (aggResult as PromiseRejectedResult).reason ??
        (listResult as PromiseRejectedResult).reason;
      setError(
        reason instanceof Error ? reason.message : "Failed to load sentiment.",
      );
    }

    setLoading(false);
  }, [token, symbol, start, end, limit, showAggregate, showList]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRefresh = useCallback(async () => {
    if (!token || !symbolId) return;
    setRefreshing(true);
    setRefreshNotice(null);
    setError(null);
    try {
      await sentimentApi.refresh(token, { symbol_id: symbolId });
      setRefreshNotice(
        "Refresh queued. New headlines will appear once the worker finishes.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to enqueue refresh.",
      );
    } finally {
      setRefreshing(false);
    }
  }, [token, symbolId]);

  const aggregateBadgeClass = aggregate
    ? labelClass(aggregate.overall_label)
    : LABEL_COLOR.neutral;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>
              {description ??
                `Recent news sentiment for ${symbol}. Updated by the Phase 17.1 pipeline.`}
            </CardDescription>
          </div>
          {showRefresh && symbolId != null && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing || !token}
            >
              {refreshing ? "Refreshing…" : "Refresh news"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!token && (
          <p className="text-sm text-muted-foreground">
            Log in to view sentiment data.
          </p>
        )}

        {token && loading && (
          <div className="space-y-3">
            <Skeleton className="h-16 w-full" />
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          </div>
        )}

        {token && !loading && error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {token && !loading && !error && refreshNotice && (
          <p className="text-sm text-emerald-600 dark:text-emerald-400">
            {refreshNotice}
          </p>
        )}

        {token && !loading && !error && showAggregate && aggregate && (
          <div className="rounded-lg border bg-muted/30 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize ${aggregateBadgeClass}`}
              >
                {aggregate.overall_label}
              </span>
              <div className="text-sm">
                <span className="text-muted-foreground">Avg score: </span>
                <span className="font-semibold tabular-nums">
                  {formatScore(aggregate.avg_score)}
                </span>
              </div>
              <div className="text-sm text-muted-foreground">
                {aggregate.total} sample{aggregate.total === 1 ? "" : "s"}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>
                <span className="text-emerald-600 dark:text-emerald-400 font-medium tabular-nums">
                  {aggregate.positive_count}
                </span>{" "}
                positive
              </span>
              <span>
                <span className="text-destructive font-medium tabular-nums">
                  {aggregate.negative_count}
                </span>{" "}
                negative
              </span>
              <span>
                <span className="font-medium tabular-nums">
                  {aggregate.neutral_count}
                </span>{" "}
                neutral
              </span>
            </div>
          </div>
        )}

        {token && !loading && !error && showList && (
          <div>
            {scores.length === 0 ? (
              <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
                No sentiment data yet for {symbol}. Configure{" "}
                <code className="font-mono text-xs">NEWSAPI_KEY</code> and run
                the worker/beat services, then click{" "}
                <span className="font-medium">Refresh news</span>.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="text-left font-medium px-3 py-2">
                        Headline
                      </th>
                      <th className="text-left font-medium px-3 py-2 hidden sm:table-cell">
                        Source
                      </th>
                      <th className="text-left font-medium px-3 py-2">Label</th>
                      <th className="text-right font-medium px-3 py-2">
                        Score
                      </th>
                      <th className="text-left font-medium px-3 py-2 hidden md:table-cell">
                        Published
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map((row) => (
                      <tr
                        key={row.id}
                        className="border-t border-border/60 hover:bg-muted/30"
                      >
                        <td className="px-3 py-2 max-w-xs">
                          {row.url ? (
                            <a
                              href={row.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="text-primary underline-offset-4 hover:underline line-clamp-2"
                              title={row.headline}
                            >
                              {row.headline}
                            </a>
                          ) : (
                            <span className="line-clamp-2" title={row.headline}>
                              {row.headline}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground hidden sm:table-cell">
                          {row.source}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize ${labelClass(row.label)}`}
                          >
                            {row.label}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatScore(row.score)}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground hidden md:table-cell whitespace-nowrap">
                          {formatPublished(row.published_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
