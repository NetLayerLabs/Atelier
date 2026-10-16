import type { Metadata, Viewport } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { AdminLogin } from "@/components/AdminLogin";
import { ToastViewport } from "@/components/ds/Toast";
import { THEME_SCRIPT } from "@/components/ds/theme-script";
import "./globals.css";

// next/font downloads these at build time and serves them from this app: no font CDN at runtime.

/** Everything: UI, body and the light display headings (weight 300, tracking -0.03em). */
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  display: "swap",
});

/** Measured values: quantities, prices, codes, telemetry. */
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Atelier - Creative Director",
  description:
    "From trend signal to pre-order: vision, diffusion and agentic production, with a human creative director in the loop.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
  colorScheme: "light dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Resolves light/dark before the first paint (see components/ds/theme.ts). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        {children}
        <AdminLogin />
        <ToastViewport />
      </body>
    </html>
  );
}
