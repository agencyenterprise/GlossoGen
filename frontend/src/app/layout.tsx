import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/features/auth/adapter/client";
import { RuntimeConfigScript } from "@/shared/config/runtime-config-script";
import { QueryProvider } from "@/shared/providers/query-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/**
 * Render every route at request time.
 *
 * The root layout reads runtime configuration, which by definition is not
 * known while the image is being built. Without this, Next.js prerenders
 * routes at build time and the config read fails (or worse, bakes in whatever
 * the build environment happened to have). Opting the layout into dynamic
 * rendering is what lets one compiled image serve any environment.
 */
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "GlossoGen",
  description: "View and explore multi-agent simulation runs",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <RuntimeConfigScript />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <AuthProvider>
          <QueryProvider>{children}</QueryProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
