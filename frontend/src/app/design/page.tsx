import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DesignShowcase } from "@/components/design/Showcase";

export const metadata: Metadata = {
  title: "Design system - Atelier",
  description: "Every Atelier design-system primitive, in the light and dark themes.",
  robots: { index: false, follow: false },
};

/**
 * Dev-only: the showcase renders the primitives with illustrative values, so it is never served in a production
 * build (404) and nothing in the judge-facing UI links to it. Run `pnpm dev` and open /design.
 */
export default function DesignPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <DesignShowcase />;
}
