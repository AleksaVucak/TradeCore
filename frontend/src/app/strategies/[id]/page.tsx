import Link from "next/link";

type StrategyDetailPageProps = {
  params: { id: string };
};

export default function StrategyDetailPage({ params }: StrategyDetailPageProps) {
  const { id } = params;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          <Link href="/strategies" className="text-muted-foreground hover:text-foreground text-sm">
            ← Back to strategies
          </Link>
          <h1 className="text-xl font-semibold tracking-tight mt-1">Strategy {id}</h1>
        </div>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <p className="text-sm text-muted-foreground">
          Strategy detail and configuration editing will be implemented in a later phase.
        </p>
      </main>
    </div>
  );
}

