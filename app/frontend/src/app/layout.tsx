import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BusinessBrain — Your AI Business Intelligence",
  description: "One AI brain for your entire business.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 antialiased">{children}</body>
    </html>
  );
}
