import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "safe-db-mcp",
  description: "A read-only SQLite MCP server with a safety layer, audit log, and text-to-SQL eval.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/try", label: "Try it" },
  { href: "/eval", label: "Eval" },
  { href: "/audit", label: "Audit log" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-stone-200 dark:border-stone-800">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3 text-sm">
            <span className="font-mono font-semibold">safe-db-mcp</span>
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="text-stone-500 hover:text-stone-900 dark:hover:text-stone-100">
                {n.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
