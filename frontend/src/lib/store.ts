"use client";

import { create } from "zustand";
import {
  analyzeTrend,
  approveDesign,
  directDesign,
  errorHint,
  errorMessage,
  generateCollection,
  generateDesigns,
  getRun,
  isNetworkError,
  refineDesign,
  retryRun,
  type AnalyzeInput,
  type Collection,
  type CreativeDirection,
  type Design,
  type PipelineRun,
  type TrendAnalysis,
} from "./api";

export type Status = "idle" | "loading" | "error" | "done";

export interface AsyncState {
  status: Status;
  error?: string;
  /** v5: setup hint when the error is a 503 (a real service is not connected / failing). */
  hint?: string;
}

/** v5: error fields for an AsyncState - the message plus the 503 setup hint, if any. */
function failure(err: unknown): { error: string; hint?: string } {
  return { error: errorMessage(err), hint: errorHint(err) };
}

export interface Round {
  id: string;
  kind: "generate" | "refine" | "direct" | "collection";
  parentDesignId?: string;
  vibe?: string;
  /** v2: the structured direction behind a "direct" round. */
  directionId?: string;
  /** v2: the collection behind a "collection" round. */
  collectionId?: string;
  designIds: string[];
}

export type IdeationMode = "concepts" | "collection";

const POLL_MS = 800;
const MAX_POLL_FAILURES = 8;

interface AtelierState {
  /** Bumped on "Start over" so in-flight responses from a previous session are dropped. */
  session: number;
  backendDown: boolean;

  analyzeInput?: AnalyzeInput;
  analyzePreviews: string[];
  analyze: AsyncState;
  trend?: TrendAnalysis;

  generate: AsyncState;
  designs: Record<string, Design>;
  labels: Record<string, string>;
  rounds: Round[];
  selectedId?: string;

  refine: AsyncState & { vibe?: string };

  // v2 - creative direction & collections
  ideationMode: IdeationMode;
  collectionGen: AsyncState & { size?: number };
  collections: Record<string, Collection>;
  direct: AsyncState & { instruction?: string };
  directions: Record<string, CreativeDirection>;

  approve: AsyncState & { quantity?: number };
  runId?: string;
  run?: PipelineRun;
  poll: AsyncState;

  setBackendDown: (down: boolean) => void;
  runAnalyze: (input: AnalyzeInput, previews?: string[]) => Promise<void>;
  retryAnalyze: () => Promise<void>;
  runGenerate: () => Promise<void>;
  select: (id: string) => void;
  runRefine: (vibe: string) => Promise<void>;
  setIdeationMode: (mode: IdeationMode) => void;
  runCollection: (size?: number) => Promise<void>;
  runDirect: (instruction: string) => Promise<void>;
  runApprove: (quantity: number) => Promise<void>;
  /** Apply a run returned by a mutation (tech pack PATCH, supplier override, PO send …). */
  updateRun: (run: PipelineRun) => void;
  /** v5: POST /api/runs/{id}/retry - resume from the first errored step, then poll again. */
  retryRun: () => Promise<void>;
  retry: AsyncState;
  resumePolling: () => void;
  reset: () => void;
}

const initial = {
  backendDown: false,
  analyzeInput: undefined,
  analyzePreviews: [] as string[],
  analyze: { status: "idle" as Status },
  trend: undefined,
  generate: { status: "idle" as Status },
  designs: {},
  labels: {},
  rounds: [],
  selectedId: undefined,
  refine: { status: "idle" as Status },
  ideationMode: "concepts" as IdeationMode,
  collectionGen: { status: "idle" as Status },
  collections: {},
  direct: { status: "idle" as Status },
  directions: {},
  approve: { status: "idle" as Status },
  runId: undefined,
  run: undefined,
  poll: { status: "idle" as Status },
  retry: { status: "idle" as Status },
};

let pollTimer: ReturnType<typeof setTimeout> | undefined;

export const useAtelier = create<AtelierState>((set, get) => {
  /** Run an async call, discarding its result if the session changed meanwhile. */
  async function guarded<T>(fn: () => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: unknown } | null> {
    const session = get().session;
    try {
      const value = await fn();
      if (get().session !== session) return null;
      if (get().backendDown) set({ backendDown: false });
      return { ok: true, value };
    } catch (error) {
      if (get().session !== session) return null;
      if (isNetworkError(error)) set({ backendDown: true });
      return { ok: false, error };
    }
  }

  function addDesigns(round: Omit<Round, "designIds">, designs: Design[]) {
    const { labels, rounds } = get();
    const nextLabels = { ...labels };
    const generations = rounds.filter((r) => r.kind === "generate").length;
    const priorLooks = rounds.filter((r) => r.kind === "collection").reduce((n, r) => n + r.designIds.length, 0);
    designs.forEach((d, i) => {
      if (d.parentDesignId && labels[d.parentDesignId]) {
        const parentLabel = labels[d.parentDesignId];
        const siblings = Object.values(nextLabels).filter(
          (l) => l.startsWith(`${parentLabel}.`) && !l.slice(parentLabel.length + 1).includes("."),
        ).length;
        nextLabels[d.id] = `${parentLabel}.${siblings + 1}`;
      } else if (round.kind === "collection") {
        // Collection looks: L1–L4; later collections continue (L5 …).
        nextLabels[d.id] = `L${priorLooks + i + 1}`;
      } else {
        // First generation: 01–04; regenerations continue numbering (05–08 …).
        nextLabels[d.id] = String(generations * designs.length + i + 1).padStart(2, "0");
      }
    });
    set((s) => ({
      designs: { ...s.designs, ...Object.fromEntries(designs.map((d) => [d.id, d])) },
      labels: nextLabels,
      rounds: [...s.rounds, { ...round, designIds: designs.map((d) => d.id) }],
    }));
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    const session = get().session;
    let failures = 0;
    const tick = async () => {
      const { runId } = get();
      if (!runId || get().session !== session) return;
      const res = await guarded(() => getRun(runId));
      if (!res) return;
      if (res.ok) {
        failures = 0;
        // A poll that left before a tech pack PATCH landed must not roll the edit back.
        const stale = (res.value.techPackRevision ?? 0) < (get().run?.techPackRevision ?? 0);
        if (!stale) set({ run: res.value });
        set({ poll: { status: res.value.status === "running" ? "loading" : "done" } });
        if (res.value.status === "running") pollTimer = setTimeout(tick, POLL_MS);
      } else {
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          set({ poll: { status: "error", ...failure(res.error) } });
        } else {
          pollTimer = setTimeout(tick, POLL_MS * Math.min(failures + 1, 4));
        }
      }
    };
    set({ poll: { status: "loading" } });
    void tick();
  }

  return {
    session: 0,
    ...initial,

    setBackendDown: (down) => set({ backendDown: down }),

    runAnalyze: async (input, previews = []) => {
      clearTimeout(pollTimer);
      set((s) => ({
        ...initial,
        backendDown: s.backendDown,
        session: s.session + 1,
        analyzeInput: input,
        analyzePreviews: previews,
        analyze: { status: "loading" },
      }));
      const res = await guarded(() => analyzeTrend(input));
      if (!res) return;
      if (res.ok) set({ trend: res.value, analyze: { status: "done" } });
      else set({ analyze: { status: "error", ...failure(res.error) } });
    },

    retryAnalyze: async () => {
      const { analyzeInput, analyzePreviews } = get();
      if (analyzeInput) await get().runAnalyze(analyzeInput, analyzePreviews);
    },

    runGenerate: async () => {
      const trend = get().trend;
      if (!trend) return;
      set({ generate: { status: "loading" } });
      const res = await guarded(() => generateDesigns({ trendId: trend.id, count: 4 }));
      if (!res) return;
      if (res.ok) {
        addDesigns({ id: `gen-${Date.now()}`, kind: "generate" }, res.value.designs);
        set({ generate: { status: "done" } });
      } else {
        set({ generate: { status: "error", ...failure(res.error) } });
      }
    },

    select: (id) => {
      if (get().approve.status === "loading" || get().runId) return;
      set((s) => ({
        selectedId: id,
        refine: { status: "idle" },
        direct: s.direct.status === "loading" ? s.direct : { status: "idle" },
      }));
    },

    setIdeationMode: (mode) => set({ ideationMode: mode }),

    runCollection: async (size = 4) => {
      const trend = get().trend;
      if (!trend) return;
      set({ ideationMode: "collection", collectionGen: { status: "loading", size } });
      const res = await guarded(() => generateCollection({ trendId: trend.id, size }));
      if (!res) return;
      if (res.ok) {
        const col = res.value;
        set((s) => ({ collections: { ...s.collections, [col.id]: col } }));
        addDesigns({ id: `col-${col.id}`, kind: "collection", collectionId: col.id }, col.designs);
        set({ collectionGen: { status: "done", size } });
      } else {
        set({ collectionGen: { status: "error", size, ...failure(res.error) } });
      }
    },

    runDirect: async (instruction) => {
      const parentId = get().selectedId;
      const text = instruction.trim();
      if (!parentId || !text || get().direct.status === "loading") return;
      set({ direct: { status: "loading", instruction: text } });
      const res = await guarded(() => directDesign(parentId, { instruction: text, count: 4 }));
      if (!res) return;
      if (res.ok) {
        const { direction, designs } = res.value;
        set((s) => ({ directions: { ...s.directions, [direction.id]: direction } }));
        addDesigns(
          { id: `dir-${direction.id}`, kind: "direct", parentDesignId: parentId, vibe: text, directionId: direction.id },
          designs,
        );
        set({ direct: { status: "done", instruction: text } });
      } else {
        set({ direct: { status: "error", instruction: text, ...failure(res.error) } });
      }
    },

    runRefine: async (vibe) => {
      const parentId = get().selectedId;
      if (!parentId || !vibe.trim()) return;
      set({ refine: { status: "loading", vibe } });
      const res = await guarded(() => refineDesign(parentId, { vibe: vibe.trim(), count: 4 }));
      if (!res) return;
      if (res.ok) {
        addDesigns(
          { id: `ref-${Date.now()}`, kind: "refine", parentDesignId: parentId, vibe: vibe.trim() },
          res.value.designs,
        );
        set({ refine: { status: "done", vibe } });
      } else {
        set({ refine: { status: "error", vibe, ...failure(res.error) } });
      }
    },

    runApprove: async (quantity) => {
      const id = get().selectedId;
      if (!id) return;
      clearTimeout(pollTimer);
      set({ approve: { status: "loading", quantity }, runId: undefined, run: undefined, poll: { status: "idle" } });
      // QA M2: the backend returns the run already active for this design instead of e-mailing suppliers twice.
      const key = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${id}-${Date.now()}`;
      const res = await guarded(() => approveDesign(id, { productionQuantity: quantity }, key));
      if (!res) return;
      if (res.ok) {
        set({ approve: { status: "done", quantity }, runId: res.value.runId });
        schedulePoll();
      } else {
        set({ approve: { status: "error", quantity, ...failure(res.error) } });
      }
    },

    updateRun: (run) => {
      if (run.id !== get().runId) return;
      set({ run });
    },

    retryRun: async () => {
      const { runId } = get();
      if (!runId || get().retry.status === "loading") return;
      // QA M3: the Evolus workflow started but its outcome is unknown - the emails may already be out.
      const unknown = get().run?.steps.find((s) => s.status === "error")?.unknownExecutionId;
      if (
        unknown &&
        !window.confirm(
          `The emails may already have been sent (Evolus execution ${unknown}, status unknown).\n\n` +
            "Check the execution in Evolus first. Send them again anyway? Suppliers may receive them twice.",
        )
      )
        return;
      set({ retry: { status: "loading" } });
      const res = await guarded(() => retryRun(runId, { confirmResend: !!unknown }));
      if (!res) return;
      if (res.ok) {
        set({ run: res.value, retry: { status: "done" } });
        schedulePoll();
      } else {
        set({ retry: { status: "error", ...failure(res.error) } });
      }
    },

    resumePolling: () => {
      if (get().runId) schedulePoll();
    },

    reset: () => {
      clearTimeout(pollTimer);
      set((s) => ({ ...initial, backendDown: s.backendDown, session: s.session + 1 }));
    },
  };
});
