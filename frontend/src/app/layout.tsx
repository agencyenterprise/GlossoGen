import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthGate } from "@/features/auth/auth-gate";
import { ClerkProviderWrapper } from "@/features/auth/clerk-provider-wrapper";
import { readServerRuntimeConfig } from "@/shared/config/runtime-config";
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
  // Read on the server so the values track the deployment rather than the
  // build. The script publishes them to the browser before hydration.
  const { clerkPublishableKey } = readServerRuntimeConfig();
  return (
    <html lang="en">
      <head>
        <RuntimeConfigScript />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ClerkProviderWrapper publishableKey={clerkPublishableKey}>
          <QueryProvider>
            <AuthGate>{children}</AuthGate>
          </QueryProvider>
        </ClerkProviderWrapper>
      </body>
    </html>
  );
}
