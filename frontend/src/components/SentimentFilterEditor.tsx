"use client";

/**
 * Phase 17.4 — strategy config UI for the optional Phase 17.3 sentiment_filter.
 *
 * Renders an enable/disable toggle and the fields that map 1:1 to the backend
 * Pydantic SentimentFilterConfig (mode, lookback, score range, sample policy).
 * The parent passes the current value (or `null` if not set) and receives the
 * updated value through `onChange`, so it stays a controlled form fragment that
 * cleanly drops into existing RSI+MA and ML signal editors.
 */

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  SENTIMENT_FILTER_DEFAULTS,
  type SentimentFilterConfig,
  type SentimentFilterMode,
} from "@/lib/api/endpoints";

type SentimentFilterEditorProps = {
  value: SentimentFilterConfig | null;
  onChange: (next: SentimentFilterConfig | null) => void;
};

const MODE_OPTIONS: { value: SentimentFilterMode; label: string; hint: string }[] = [
  {
    value: "block_negative",
    label: "Block negative",
    hint: "Block new long entries while the aggregate score is below the minimum.",
  },
  {
    value: "require_positive",
    label: "Require positive",
    hint: "Only allow new long entries while the aggregate score is strictly above the minimum.",
  },
  {
    value: "threshold",
    label: "Threshold range",
    hint: "Only allow new long entries while the aggregate score is between min and max.",
  },
];

function validate(cfg: SentimentFilterConfig): string | null {
  if (cfg.lookback_hours < 1 || cfg.lookback_hours > 720) {
    return "Lookback hours must be between 1 and 720.";
  }
  if (cfg.min_score < -1 || cfg.min_score > 1) {
    return "Min score must be between -1 and 1.";
  }
  if (cfg.max_score < -1 || cfg.max_score > 1) {
    return "Max score must be between -1 and 1.";
  }
  if (cfg.mode === "threshold" && cfg.max_score < cfg.min_score) {
    return "Max score must be greater than or equal to min score for threshold mode.";
  }
  if (cfg.min_samples < 1 || cfg.min_samples > 1000) {
    return "Min samples must be between 1 and 1000.";
  }
  return null;
}

export function SentimentFilterEditor({
  value,
  onChange,
}: SentimentFilterEditorProps) {
  const enabled = value?.enabled ?? false;
  const cfg = value ?? { ...SENTIMENT_FILTER_DEFAULTS, enabled: false };
  const validationError = enabled ? validate(cfg) : null;

  const update = (patch: Partial<SentimentFilterConfig>) => {
    const next: SentimentFilterConfig = { ...cfg, ...patch };
    onChange(next);
  };

  const toggleEnabled = (nextEnabled: boolean) => {
    if (!nextEnabled) {
      // Disable: clear by emitting null so config JSON stays clean.
      onChange(null);
      return;
    }
    // Enable: instantiate defaults the first time.
    onChange({ ...SENTIMENT_FILTER_DEFAULTS, enabled: true });
  };

  const activeMode = MODE_OPTIONS.find((m) => m.value === cfg.mode) ?? MODE_OPTIONS[0];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground">
            Sentiment filter (optional)
          </h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-prose">
            Gate new long entries on aggregate news sentiment from the Phase 17
            pipeline. Exits (stop-loss, take-profit, sell signals) are never
            blocked.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer self-end pb-1">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => toggleEnabled(e.target.checked)}
            className="rounded border-input"
          />
          Enabled
        </label>
      </div>

      {enabled && (
        <div className="rounded-lg border bg-muted/20 p-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sentiment_filter_mode">Mode</Label>
              <select
                id="sentiment_filter_mode"
                value={cfg.mode}
                onChange={(e) =>
                  update({ mode: e.target.value as SentimentFilterMode })
                }
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {MODE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{activeMode.hint}</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sentiment_filter_lookback">Lookback (hours)</Label>
              <Input
                id="sentiment_filter_lookback"
                type="number"
                min={1}
                max={720}
                step={1}
                value={cfg.lookback_hours}
                onChange={(e) =>
                  update({ lookback_hours: Number(e.target.value) || 1 })
                }
              />
              <p className="text-xs text-muted-foreground">
                Window aggregated over published-before-bar timestamps (no look-ahead).
              </p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="sentiment_filter_min_score">Min score</Label>
              <Input
                id="sentiment_filter_min_score"
                type="number"
                min={-1}
                max={1}
                step={0.05}
                value={cfg.min_score}
                onChange={(e) => update({ min_score: Number(e.target.value) })}
              />
            </div>
            {cfg.mode === "threshold" && (
              <div className="space-y-1.5">
                <Label htmlFor="sentiment_filter_max_score">Max score</Label>
                <Input
                  id="sentiment_filter_max_score"
                  type="number"
                  min={-1}
                  max={1}
                  step={0.05}
                  value={cfg.max_score}
                  onChange={(e) =>
                    update({ max_score: Number(e.target.value) })
                  }
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="sentiment_filter_min_samples">Min samples</Label>
              <Input
                id="sentiment_filter_min_samples"
                type="number"
                min={1}
                max={1000}
                step={1}
                value={cfg.min_samples}
                onChange={(e) =>
                  update({ min_samples: Number(e.target.value) || 1 })
                }
              />
              <p className="text-xs text-muted-foreground">
                Minimum rows required inside the lookback window.
              </p>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={cfg.allow_when_missing}
              onChange={(e) =>
                update({ allow_when_missing: e.target.checked })
              }
              className="rounded border-input"
            />
            Allow trades when sentiment data is missing
            <span className="text-xs text-muted-foreground">
              (uncheck to fail closed)
            </span>
          </label>

          {validationError && (
            <p className="text-xs text-destructive">{validationError}</p>
          )}
        </div>
      )}
    </div>
  );
}

/** Convert an unknown JSON blob from the backend into a SentimentFilterConfig (or null). */
export function sentimentFilterFromJson(
  raw: unknown,
): SentimentFilterConfig | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const mode = obj.mode;
  if (
    mode !== "block_negative" &&
    mode !== "require_positive" &&
    mode !== "threshold"
  ) {
    return null;
  }
  return {
    enabled: typeof obj.enabled === "boolean" ? obj.enabled : true,
    mode,
    lookback_hours:
      typeof obj.lookback_hours === "number"
        ? obj.lookback_hours
        : SENTIMENT_FILTER_DEFAULTS.lookback_hours,
    min_score:
      typeof obj.min_score === "number"
        ? obj.min_score
        : SENTIMENT_FILTER_DEFAULTS.min_score,
    max_score:
      typeof obj.max_score === "number"
        ? obj.max_score
        : SENTIMENT_FILTER_DEFAULTS.max_score,
    min_samples:
      typeof obj.min_samples === "number"
        ? obj.min_samples
        : SENTIMENT_FILTER_DEFAULTS.min_samples,
    allow_when_missing:
      typeof obj.allow_when_missing === "boolean"
        ? obj.allow_when_missing
        : SENTIMENT_FILTER_DEFAULTS.allow_when_missing,
  };
}
