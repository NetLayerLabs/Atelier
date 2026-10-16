"use client";

import { useEffect, useState } from "react";
import { IconArrowUpRight, InlineAlert, LinkButton } from "@/components/ds";
import { getWorkspaceStatus, type WorkspaceStatus } from "@/lib/workspace";

/** v5: the workspace readiness (null while unknown / unreachable - the backend still enforces it on approve). */
export function useWorkspaceStatus(pollMs = 0): WorkspaceStatus | null {
  const [st, setSt] = useState<WorkspaceStatus | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      getWorkspaceStatus()
        .then((s) => live && setSt(s))
        .catch(() => undefined);
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    const id = pollMs ? setInterval(load, pollMs) : undefined;
    return () => {
      live = false;
      window.removeEventListener("focus", onFocus);
      if (id) clearInterval(id);
    };
  }, [pollMs]);
  return st;
}

/** Shown where a design is approved: what is missing before Atelier may email the brand's suppliers. */
export function WorkspaceGate({ status }: { status: WorkspaceStatus | null }) {
  if (!status || status.ready) return null;
  return (
    <InlineAlert
      tone="warn"
      data-demo="workspace-gate"
      title="Set up the Brand workspace first"
      className="mt-5"
      action={
        <LinkButton
          href="/workspace"
          target="_blank"
          rel="noopener"
          size="sm"
          variant="secondary"
          trailing={<IconArrowUpRight size={14} />}
        >
          Open Brand workspace (new tab)
        </LinkButton>
      }
    >
      Approving sends RFQs to your real suppliers, so Atelier needs {status.missing.join("; ")}.
    </InlineAlert>
  );
}
