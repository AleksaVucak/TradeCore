import Link from "next/link";

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="min-h-screen bg-background">
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-semibold mt-4">Run {id.slice(0, 8)}…</h1>
        <p className="text-muted-foreground mt-2">
          Run detail page with charts and metrics (Phase 8).
        </p>
      </main>
    </div>
  );
}
