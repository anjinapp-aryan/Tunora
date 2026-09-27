import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "Tunora — AI Music Studio",
  description: "Describe a song and Tunora creates it, locally.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <header className="border-b border-border/60">
          <div className="mx-auto flex h-14 w-full max-w-3xl items-center px-4 sm:px-6">
            <Link href="/create" className="text-sm font-semibold tracking-[0.2em]">
              TUNORA
            </Link>
            <span className="ml-3 hidden text-xs text-muted-foreground sm:inline">AI Music Studio</span>
            <nav aria-label="Main" className="ml-auto flex gap-5 text-sm">
              <Link href="/create" className="text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">Create</Link>
              <Link href="/library" className="text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">Library</Link>
              <Link href="/projects" className="text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">Projects</Link>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
