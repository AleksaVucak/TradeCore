"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api/endpoints";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const hasToken = Boolean(token);

  const [status, setStatus] = useState<"loading" | "success" | "error">(() =>
    hasToken ? "loading" : "error",
  );
  const [message, setMessage] = useState(() =>
    hasToken ? "" : "No verification token provided.",
  );

  useEffect(() => {
    if (!token) return;

    let cancelled = false;

    void (async () => {
      try {
        const res = await authApi.verifyEmail(token);
        if (!cancelled) {
          setMessage(res.message);
          setStatus("success");
        }
      } catch (err) {
        if (!cancelled) {
          setMessage(err instanceof Error ? err.message : "Verification failed.");
          setStatus("error");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6 text-center">
        {status === "loading" && (
          <>
            <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-muted border-t-primary" />
            <p className="text-muted-foreground">Verifying your email...</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-500/10">
              <svg className="h-7 w-7 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <h1 className="text-2xl font-semibold">Email verified</h1>
            <p className="text-muted-foreground text-sm">{message}</p>
            <Button asChild className="w-full">
              <Link href="/login">Sign in</Link>
            </Button>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
              <svg className="h-7 w-7 text-destructive" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-semibold">Verification failed</h1>
            <p className="text-muted-foreground text-sm">{message}</p>
            <div className="space-y-2">
              <Button asChild variant="outline" className="w-full">
                <Link href="/register">Back to register</Link>
              </Button>
              <Button asChild className="w-full">
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-muted border-t-primary" />
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
