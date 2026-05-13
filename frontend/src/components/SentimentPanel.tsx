"use client";

/**
 * Phase 17.4+ — reusable sentiment display component.
 *
 * Headlines use **page-based pagination**: `limit` rows per page (default 10),
 * only the current page is fetched (`offset` on the API). Prev / Next rotate
 * pages so at most `limit` rows are shown at once.
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
  token: string | null;
  symbol: string;
  symbolId?: number | null;
  start?: string | null;
  end?: string | null;
  limit?: number;
  title?: string;
  description?: string;
  showRefresh?: boolean;
  showAggregate?: boolean;
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
  limit = 10,
  title = "News sentiment",
  description,
  showRefresh = false,
  showAggregate = true,
  showList = true,
}: SentimentPanelProps) {
  const [page, setPage] = useState(1);
  const [aggregate, setAggregate] = useState<SentimentAggregateOut | null>(null);
  const [scores, setScores] = useState<SentimentScoreOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  const isDateFiltered = Boolean(start || end);

  useEffect(() => {
    setPage(1);
  }, [limit, symbol, start, end]);

  const load = useCallback(
    async (pageOverride?: number) => {
      const currentPage = pageOverride ?? page;
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
            offset: (currentPage - 1) * limit,
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
        setAggregate(null);
      }

      if (listResult.status === "fulfilled") {
        const data = listResult.value as { scores: SentimentScoreOut[] } | null;
        setScores(data?.scores ?? []);
      } else if (showList) {
        setScores([]);
      }

      const aggFailed = showAggregate && aggResult.status === "rejected";
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
    },
    [token, symbol, start, end, page, limit, showAggregate, showList],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const handleRefresh = useCallback(async () => {
    if (!token || !symbolId) return;
    setRefreshing(true);
    setRefreshNotice(null);
    setError(null);
    try {
      const res = await sentimentApi.refresh(
        token,
        { symbol_id: symbolId },
        { sync: true },
      );

      if (res.fetch_status && res.fetch_status !== "ok") {
        const detail = res.fetch_detail || "Unknown issue.";
        setRefreshNotice(null);
        setError(detail);
      } else if (res.status === "completed") {
        const newCount = res.new ?? 0;
        if (newCount > 0) {
          setRefreshNotice(
            `Refresh complete — ${newCount} new headline${newCount === 1 ? "" : "s"} scored and stored.`,
          );
          setPage(1);
          await load(1);
        } else {
          setRefreshNotice(
            "Refresh complete — no new headlines found. All recent articles were already stored.",
          );
        }
      } else {
        setRefreshNotice(
          "Refresh queued. New headlines will appear once the worker finishes.",
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to enqueue refresh.",
      );
    } finally {
      setRefreshing(false);
    }
  }, [token, symbolId, load]);

  const aggregateBadgeClass = aggregate
    ? labelClass(aggregate.overall_label)
    : LABEL_COLOR.neutral;

  const totalAvailable = aggregate?.total ?? 0;
  const totalPages =
    showAggregate && aggregate && totalAvailable > 0
      ? Math.max(1, Math.ceil(totalAvailable / limit))
      : null;
  const rangeStart =
    scores.length === 0 ? 0 : (page - 1) * limit + 1;
  const rangeEnd = scores.length === 0 ? 0 : (page - 1) * limit + scores.length;
  const hasPrev = page > 1;
  const hasNext =
    totalPages != null ? page < totalPages : scores.length === limit;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>
              {description ??
                `Recent news sentiment for ${symbol}. Updated by the sentiment pipeline.`}
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
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive space-y-1">
            <p className="font-medium">Sentiment refresh issue</p>
            <p>{error}</p>
          </div>
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
              <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground space-y-2">
                {isDateFiltered ? (
                  <>
                    <p>
                      No sentiment data for <strong>{symbol}</strong> in the
                      selected date range.
                    </p>
                    <p className="text-xs">
                      The sentiment pipeline only stores headlines from the last
                      7 days by default. If this backtest covers an older window,
                      no matching headlines will exist. Run a refresh on the{" "}
                      <strong>Market Data</strong> page to populate recent data,
                      or re-run the backtest over a more recent period.
                    </p>
                  </>
                ) : (
                  <>
                    <p>
                      No sentiment data yet for <strong>{symbol}</strong>.
                    </p>
                    <ol className="list-decimal list-inside space-y-1 text-xs">
                      <li>
                        Set <code className="font-mono">NEWSAPI_KEY</code> in
                        your project root{" "}
                        <code className="font-mono">.env</code> file (free at{" "}
                        <a
                          href="https://newsapi.org/register"
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-primary underline-offset-4 hover:underline"
                        >
                          newsapi.org
                        </a>
                        ).
                      </li>
                      <li>
                        Restart the stack:{" "}
                        <code className="font-mono">
                          docker compose up --build
                        </code>
                      </li>
                      <li>
                        Click{" "}
                        <span className="font-medium">Refresh news</span> above.
                        Results appear in seconds.
                      </li>
                    </ol>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    {scores.length > 0 ? (
                      <>
                        Showing{" "}
                        <span className="font-medium tabular-nums text-foreground">
                          {rangeStart}
                        </span>
                        –
                        <span className="font-medium tabular-nums text-foreground">
                          {rangeEnd}
                        </span>
                        {totalAvailable > 0 && (
                          <>
                            {" "}
                            of{" "}
                            <span className="font-medium tabular-nums text-foreground">
                              {totalAvailable}
                            </span>
                          </>
                        )}{" "}
                        headline{scores.length === 1 ? "" : "s"}
                      </>
                    ) : (
                      <span>No headlines on this page.</span>
                    )}
                  </span>
                  {totalPages != null && totalPages > 1 && (
                    <span className="tabular-nums">
                      Page{" "}
                      <span className="font-medium text-foreground">{page}</span> of{" "}
                      <span className="font-medium text-foreground">{totalPages}</span>
                    </span>
                  )}
                </div>
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
                        <th className="text-left font-medium px-3 py-2">
                          Label
                        </th>
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
                              <span
                                className="line-clamp-2"
                                title={row.headline}
                              >
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
                {(hasPrev || hasNext) && (
                  <div className="flex flex-wrap items-center justify-center gap-3">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={loading || !hasPrev}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </Button>
                    {totalPages == null && hasNext && (
                      <span className="text-xs text-muted-foreground">Page {page}</span>
                    )}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={loading || !hasNext}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
