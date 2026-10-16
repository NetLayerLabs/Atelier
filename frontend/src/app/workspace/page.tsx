import type { Metadata } from "next";
import { BrandWorkspace } from "@/components/workspace/BrandWorkspace";

export const metadata: Metadata = {
  title: "Brand workspace - Atelier",
  description: "The brand's own profile, brand book, suppliers, price list, guardrails and sales history.",
};

export default function WorkspacePage() {
  return <BrandWorkspace />;
}
