import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthGate } from "@/features/auth/auth-gate";
import { ClerkProviderWrapper } from "@/features/auth/clerk-provider-wrapper";
import { QueryProvider } from "@/shared/providers/query-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GlossoGen",
  description: "View and explore multi-agent simulation runs",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ClerkProviderWrapper>
          <QueryProvider>
            <AuthGate>{children}</AuthGate>
          </QueryProvider>
        </ClerkProviderWrapper>
      </body>
    </html>
  );
}
