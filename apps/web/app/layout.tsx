import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "TransLoka",
  description: "Local-First Personal PDF Translation Application",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen flex-col">
          <header className="border-b border-slate-200 bg-white px-6 py-4">
            <nav
              aria-label="Primary navigation"
              className="mx-auto flex w-full max-w-6xl items-center justify-between"
            >
              <Link className="font-semibold tracking-tight text-slate-900" href="/">
                TransLoka
              </Link>
              <Link
                className="text-sm font-medium text-slate-600 hover:text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-slate-900"
                href="/settings/system"
              >
                System health
              </Link>
            </nav>
          </header>
          <div className="flex flex-1 items-start justify-center px-6 py-12">{children}</div>
        </div>
      </body>
    </html>
  );
}
