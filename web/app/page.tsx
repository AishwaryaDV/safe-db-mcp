import Link from "next/link";

const CARDS = [
  {
    href: "/try",
    title: "Try it",
    body: "Ask a plain-English question. Claude plans the SQL, the server runs it read-only, and you watch every tool call stream back live.",
  },
  {
    href: "/eval",
    title: "Eval",
    body: "How often does text-to-SQL get the right answer through this interface? Browse runs, metrics, and the exact questions that passed or failed.",
  },
  {
    href: "/audit",
    title: "Audit log",
    body: "Every query the server saw, including the ones the safety layer blocked, with timing and row counts.",
  },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">A safe database interface for LLMs</h1>
        <p className="max-w-2xl text-stone-500">
          safe-db-mcp exposes SQLite over the Model Context Protocol with a safety layer that only
          allows read-only queries, caps rows and runtime, logs everything, and suggests fixes when a
          query is malformed. The eval measures how accurate text-to-SQL is through that interface.
        </p>
      </section>
      <section className="grid gap-4 sm:grid-cols-3">
        {CARDS.map((c) => (
          <Link key={c.href} href={c.href} className="card transition hover:border-stone-400">
            <h2 className="mb-2 font-medium">{c.title}</h2>
            <p className="text-sm text-stone-500">{c.body}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
