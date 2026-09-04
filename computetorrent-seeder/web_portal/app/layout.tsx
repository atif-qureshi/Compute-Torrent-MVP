import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ComputeTorrent — Requestor Portal",
  description: "Submit tasks, monitor swarms, and download results.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        <nav className="border-b border-gray-800 bg-gray-900 px-6 py-3 flex items-center gap-6">
          <span className="font-bold text-blue-400 text-lg tracking-tight">ComputeTorrent</span>
          <a href="/submit"  className="text-sm text-gray-300 hover:text-white transition-colors">Submit Task</a>
          <a href="/history" className="text-sm text-gray-300 hover:text-white transition-colors">History</a>
        </nav>
        <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
