import type { Metadata } from "next";
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
            <p className="font-semibold tracking-tight text-slate-900">TransLoka</p>
          </header>
          <div className="flex flex-1 items-center justify-center px-6 py-16">{children}</div>
        </div>
      </body>
    </html>
  );
}
