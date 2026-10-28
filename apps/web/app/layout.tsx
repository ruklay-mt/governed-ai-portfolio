import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { SITE } from "@/lib/site";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: `${SITE.author} · Governed AI`, template: `%s · ${SITE.author}` },
  description:
    "An AI agent over a fictional company's data. Answers change by role, and every answer shows its evidence.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="border-b border-border">
          <nav className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold">
              {SITE.author}
            </Link>
            <div className="flex gap-4 text-muted">
              <Link href="/assistant" className="hover:text-foreground">
                Assistant demo
              </Link>
              <a href={SITE.repoUrl} className="hover:text-foreground">
                GitHub
              </a>
            </div>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
