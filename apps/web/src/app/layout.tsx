import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import { AtomChatWidget } from "@/components/chat/AtomChatWidget";

export const metadata: Metadata = {
  title: "Thesis Residency Platform",
  description: "Vault navigation, ingestion, and live analytics"
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
        <AtomChatWidget />
      </body>
    </html>
  );
}
