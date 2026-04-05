"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { authApi, type User } from "@/lib/api/endpoints";
import { getToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Stage = "idle" | "setup" | "confirm" | "disable";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const [stage, setStage] = useState<Stage>("idle");
  const [secret, setSecret] = useState("");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchUser = useCallback(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    setLoading(true);
    authApi
      .me(token)
      .then(setUser)
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  function resetForm() {
    setCode("");
    setPassword("");
    setError("");
    setSuccess("");
  }

  async function handleStartSetup() {
    const token = getToken();
    if (!token) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await authApi.twoFactorSetupStart(token);
      setSecret(res.secret);
      setOtpauthUri(res.otpauth_uri);
      setStage("confirm");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start 2FA setup.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirm() {
    const token = getToken();
    if (!token) return;
    if (code.length !== 6) {
      setError("Please enter a 6-digit code.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await authApi.twoFactorSetupConfirm(code, token);
      setSuccess(res.message);
      setStage("idle");
      resetForm();
      fetchUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirmation failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDisable() {
    const token = getToken();
    if (!token) return;
    if (code.length !== 6) {
      setError("Please enter a 6-digit code.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await authApi.twoFactorDisable(password, code, token);
      setSuccess(res.message);
      setStage("idle");
      resetForm();
      fetchUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable 2FA.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="max-w-2xl mx-auto py-12 px-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  if (!user) return null;

  return (
    <main className="max-w-2xl mx-auto py-12 px-6 flex flex-col gap-8">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

      {/* ── Account overview ─────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Your account details</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Email</span>
            <span>{user.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Email verified</span>
            <span>{user.email_verified ? "Yes" : "No"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Two-factor authentication</span>
            <span className={user.totp_enabled ? "text-green-600 dark:text-green-500" : ""}>
              {user.totp_enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* ── 2FA section ──────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Two-Factor Authentication</CardTitle>
          <CardDescription>
            {user.totp_enabled
              ? "2FA is active. You need an authenticator app code to log in."
              : "Add an extra layer of security by enabling TOTP-based 2FA."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {success && (
            <div className="rounded-md border border-green-700/30 bg-green-950/20 px-4 py-3 text-sm text-green-400">
              {success}
            </div>
          )}
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* ── Idle: show enable/disable button ─── */}
          {stage === "idle" && !user.totp_enabled && (
            <Button onClick={handleStartSetup} disabled={submitting}>
              {submitting ? "Starting…" : "Enable 2FA"}
            </Button>
          )}
          {stage === "idle" && user.totp_enabled && (
            <Button
              variant="destructive"
              onClick={() => {
                resetForm();
                setSuccess("");
                setStage("disable");
              }}
            >
              Disable 2FA
            </Button>
          )}

          {/* ── Confirm stage: QR code + code input ─── */}
          {stage === "confirm" && (
            <div className="flex flex-col gap-5">
              <p className="text-sm text-muted-foreground">
                Scan the QR code below with your authenticator app (Google Authenticator, Authy, etc.), then enter the 6-digit code to confirm.
              </p>

              <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-muted/30 p-6">
                {/* QR code rendered as an <img> via Google Charts API (no extra deps) */}
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(otpauthUri)}`}
                  alt="Scan this QR code with your authenticator app"
                  width={200}
                  height={200}
                  className="rounded-md"
                />
                <div className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
                  <span>Can&apos;t scan? Enter this key manually:</span>
                  <code className="select-all rounded bg-muted px-2 py-1 font-mono text-sm">
                    {secret}
                  </code>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="totp-code">6-digit code</Label>
                <Input
                  id="totp-code"
                  placeholder="000000"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="max-w-[200px] font-mono tracking-widest text-center text-lg"
                  autoComplete="one-time-code"
                />
              </div>

              <div className="flex gap-3">
                <Button onClick={handleConfirm} disabled={submitting || code.length !== 6}>
                  {submitting ? "Verifying…" : "Confirm & Enable"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setStage("idle");
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {/* ── Disable stage: password + code ─── */}
          {stage === "disable" && (
            <div className="flex flex-col gap-5">
              <p className="text-sm text-muted-foreground">
                To disable 2FA, enter your account password and a current authenticator code.
              </p>

              <div className="flex flex-col gap-2">
                <Label htmlFor="disable-password">Password</Label>
                <Input
                  id="disable-password"
                  type="password"
                  placeholder="Your account password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="max-w-[320px]"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="disable-code">6-digit code</Label>
                <Input
                  id="disable-code"
                  placeholder="000000"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="max-w-[200px] font-mono tracking-widest text-center text-lg"
                  autoComplete="one-time-code"
                />
              </div>

              <div className="flex gap-3">
                <Button
                  variant="destructive"
                  onClick={handleDisable}
                  disabled={submitting || code.length !== 6 || !password}
                >
                  {submitting ? "Disabling…" : "Disable 2FA"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setStage("idle");
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
