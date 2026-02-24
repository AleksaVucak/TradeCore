import Link from "next/link";

export default function StrategiesPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold tracking-tight mt-2">Strategies</h1>
      </header>
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <p className="text-muted-foreground">Strategy list and create form (Phase 5).</p>
      </main>
    </div>
  );
}
