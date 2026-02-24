import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-xl font-semibold tracking-tight">TradeCore</h1>
        <p className="text-sm text-muted-foreground">
          Strategy research and paper-trading for crypto spot
        </p>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-semibold">Dashboard</h2>
          <p className="text-muted-foreground">
            Overview and quick actions
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total runs
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">—</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Strategies
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">—</span>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Quick actions
              </CardTitle>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Link
                href="/backtests"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                New backtest
              </Link>
              <span className="text-muted-foreground">·</span>
              <Link
                href="/strategies"
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                New strategy
              </Link>
            </CardContent>
          </Card>
        </div>
        <div className="mt-8">
          <Card>
            <CardHeader>
              <CardTitle>Recent runs</CardTitle>
              <CardDescription>Your latest backtest runs</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                No runs yet. Create a backtest to get started.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
