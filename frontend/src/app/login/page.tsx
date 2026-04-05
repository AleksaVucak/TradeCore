"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api/endpoints";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [unverified, setUnverified] = useState(false);
  const [totpRequired, setTotpRequired] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendMsg, setResendMsg] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setUnverified(false);
    setResendMsg("");
    setLoading(true);
    try {
      const code = totpRequired ? totpCode : undefined;
      const { access_token } = await authApi.login(email, password, code);
      setToken(access_token);
      window.dispatchEvent(new CustomEvent("tradecore:auth"));
      router.push("/");
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed.";
      if (msg.toLowerCase().includes("not verified")) {
        setUnverified(true);
      } else if (msg.toLowerCase().includes("code required")) {
        setTotpRequired(true);
        setError("");
        setLoading(false);
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setResendLoading(true);
    setResendMsg("");
    try {
      const res = await authApi.resendVerification(email, password);
      setResendMsg(res.message);
    } catch (err) {
      setResendMsg(err instanceof Error ? err.message : "Could not resend email.");
    } finally {
      setResendLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold">TradeCore</h1>
          <p className="text-muted-foreground text-sm mt-1">Sign in to your account</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              disabled={loading || totpRequired}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              disabled={loading || totpRequired}
            />
          </div>

          {totpRequired && (
            <div className="space-y-2">
              <Label htmlFor="totp-code">Authenticator code</Label>
              <p className="text-xs text-muted-foreground">
                Open your authenticator app and enter the 6-digit code.
              </p>
              <Input
                id="totp-code"
                placeholder="000000"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="max-w-[200px] font-mono tracking-widest text-center text-lg"
                autoComplete="one-time-code"
                autoFocus
              />
            </div>
          )}

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {unverified && (
            <div className="space-y-2">
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={handleResend}
                disabled={resendLoading}
              >
                {resendLoading ? "Sending..." : "Resend verification email"}
              </Button>
              {resendMsg && (
                <p className="text-sm text-muted-foreground">{resendMsg}</p>
              )}
            </div>
          )}
          <Button type="submit" className="w-full" disabled={loading || (totpRequired && totpCode.length !== 6)}>
            {loading ? "Signing in..." : totpRequired ? "Verify & Sign in" : "Sign in"}
          </Button>
          {totpRequired && (
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => {
                setTotpRequired(false);
                setTotpCode("");
                setError("");
              }}
            >
              Back
            </Button>
          )}
        </form>
        <p className="text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-primary underline-offset-4 hover:underline">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
