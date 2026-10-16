"use client";

// Shared backend health: the header polls GET /api/health and publishes the result here, so the landing's status
// strip and architecture diagram show the same connection state (connected / unreachable / not connected, and any
// FAKE upstream) without a second poller.

import { create } from "zustand";
import type { HealthResponse } from "./api";

export type HealthState =
  | { kind: "checking" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "down" }
  | { kind: "error" };

export const useHealth = create<{ health: HealthState; setHealth: (h: HealthState) => void }>((set) => ({
  health: { kind: "checking" },
  setHealth: (health) => set({ health }),
}));

/** Display names for the services in GET /api/health, in pipeline order. */
export const SERVICE_ORDER = [
  "vision",
  "diffusion",
  "llm",
  "evolus_agent",
  "evolus_outreach",
  "evolus_extractor",
  "evolus_po",
  "evolus_shopify",
  "shopify",
] as const;

export const SERVICE_SHORT: Record<string, string> = {
  vision: "Vision",
  diffusion: "Diffusion",
  llm: "LLM",
  evolus_outreach: "Evolus outreach",
  evolus_agent: "Evolus agent",
  evolus_extractor: "Evolus extractor",
  evolus_po: "Evolus PO",
  evolus_shopify: "Evolus Shopify",
  shopify: "Shopify",
};
