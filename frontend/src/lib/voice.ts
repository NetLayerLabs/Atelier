"use client";

// v3: customer-voice state. Kept apart from the main store on purpose: reading a new trend resets the
// session there, but the merchant's customer data (and the changes they picked) should survive it.
import { create } from "zustand";
import {
  analyseVoiceSample,
  applyVoiceChanges,
  errorMessage,
  uploadVoice,
  type CustomerEvidence,
  type VoiceInsights,
} from "./api";

type Status = "idle" | "loading" | "error" | "done";

export type VoiceInput = { kind: "file"; file: File } | { kind: "sample"; key: string; title: string };

interface VoiceState {
  status: Status;
  error?: string;
  input?: VoiceInput;
  insights?: VoiceInsights;
  selected: string[];
  apply: {
    status: Status;
    error?: string;
    /** Trend the selection is attached to; "pending" = applies as soon as a trend is read. */
    trendId?: string;
    pending: boolean;
    applied: CustomerEvidence[];
  };

  analyse: (input: VoiceInput) => Promise<void>;
  toggle: (changeId: string) => void;
  /** Attach the selection to a trend (every design from it inherits it), or queue it until there is one. */
  applyTo: (trendId: string | undefined) => Promise<void>;
  clear: () => void;
}

const idleApply = { status: "idle" as Status, pending: false, applied: [] as CustomerEvidence[] };
let token = 0;

export const useVoice = create<VoiceState>((set, get) => ({
  status: "idle",
  selected: [],
  apply: idleApply,

  analyse: async (input) => {
    const mine = ++token;
    set({ status: "loading", error: undefined, input, insights: undefined, selected: [], apply: idleApply });
    try {
      const insights =
        input.kind === "file" ? await uploadVoice(input.file) : await analyseVoiceSample(input.key);
      if (mine !== token) return;
      // Pre-select the strongest evidence; contradicting changes are never pre-selected together.
      const picked: string[] = [];
      for (const c of insights.recommendedChanges) {
        if (picked.length >= 3 || c.confidence === "low") continue;
        if (c.conflictsWith.some((id) => picked.includes(id))) continue;
        picked.push(c.id);
      }
      set({ status: "done", insights, selected: picked });
    } catch (err) {
      if (mine !== token) return;
      set({ status: "error", error: errorMessage(err) });
    }
  },

  toggle: (changeId) => {
    const { insights, selected } = get();
    const change = insights?.recommendedChanges.find((c) => c.id === changeId);
    if (!change) return;
    const next = selected.includes(changeId)
      ? selected.filter((id) => id !== changeId)
      : [...selected.filter((id) => !change.conflictsWith.includes(id)), changeId];
    // Edits after applying mark the attachment stale until the merchant applies again.
    set((s) => ({ selected: next, apply: s.apply.status === "done" ? { ...s.apply, status: "idle" } : s.apply }));
  },

  applyTo: async (trendId) => {
    const { insights, selected } = get();
    if (!insights) return;
    if (!trendId) {
      set({ apply: { ...idleApply, pending: true } });
      return;
    }
    const mine = token;
    set((s) => ({ apply: { ...s.apply, status: "loading", error: undefined, pending: false } }));
    try {
      const res = await applyVoiceChanges(insights.id, { changeIds: selected, trendId });
      if (mine !== token) return;
      set({ apply: { status: "done", trendId, pending: false, applied: res.applied } });
    } catch (err) {
      if (mine !== token) return;
      set((s) => ({ apply: { ...s.apply, status: "error", error: errorMessage(err) } }));
    }
  },

  clear: () => {
    const { insights, apply } = get();
    if (insights && apply.trendId) {
      // Detach what was applied, so a later approval doesn't carry evidence the merchant discarded.
      void applyVoiceChanges(insights.id, { changeIds: [], trendId: apply.trendId }).catch(() => undefined);
    }
    token++;
    set({ status: "idle", error: undefined, input: undefined, insights: undefined, selected: [], apply: idleApply });
  },
}));
