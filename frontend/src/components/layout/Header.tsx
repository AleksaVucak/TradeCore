"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api/endpoints";
import { getToken, removeToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ email: string } | null>(null);
  const [loading, setLoading] = useState(true);

  function checkAuth() {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    authApi.me(token).then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }

  useEffect(() => {
    checkAuth();
  }, [pathname]);

  useEffect(() => {
    const handler = () => checkAuth();
    window.addEventListener("tradecore:auth", handler);
    return () => window.removeEventListener("tradecore:auth", handler);
  }, []);

  function handleLogout() {
    removeToken();
    setUser(null);
    router.push("/");
    router.refresh();
  }

  const isAuthPage = pathname === "/login" || pathname === "/register";

  return (
    <header className="border-b border-border px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <Link href="/" className="text-xl font-semibold tracking-tight">
          TradeCore
        </Link>
        {!isAuthPage && (
          <nav className="flex gap-4 text-sm">
            <Link
              href="/"
              className={pathname === "/" ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}
            >
              Dashboard
            </Link>
            <Link
              href="/strategies"
              className={pathname === "/strategies" ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}
            >
              Strategies
            </Link>
            <Link
              href="/backtests"
              className={pathname === "/backtests" ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}
            >
              Backtests
            </Link>
            <Link
              href="/market-data"
              className={pathname === "/market-data" ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}
            >
              Market data
            </Link>
          </nav>
        )}
      </div>
      <div className="flex items-center gap-3">
        {loading ? (
          <span className="text-sm text-muted-foreground">…</span>
        ) : user ? (
          <>
            <span className="text-sm text-muted-foreground">{user.email}</span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              Logout
            </Button>
          </>
        ) : !isAuthPage ? (
          <>
            <Link href="/login">
              <Button variant="ghost" size="sm">Login</Button>
            </Link>
            <Link href="/register">
              <Button size="sm">Register</Button>
            </Link>
          </>
        ) : null}
      </div>
    </header>
  );
}
