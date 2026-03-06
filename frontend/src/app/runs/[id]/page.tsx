import Link from "next/link";
import { RunDetailClient } from "./RunDetailClient";

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="min-h-screen bg-background">
      <main className="container mx-auto max-w-5xl px-6 py-8">
        <Link
          href="/backtests"
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          ← Run history
        </Link>
        <RunDetailClient runId={id} />
      </main>
    </div>
  );
}
