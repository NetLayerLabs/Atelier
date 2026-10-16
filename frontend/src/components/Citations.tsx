"use client";

// v3: knowledge-library sources (brand book, supplier catalogue) behind an agent output.

import { useState } from "react";
import { Badge, cx, Label } from "@/components/ds";
import type { Citation } from "@/lib/api";

export function Citations({ items, className }: { items?: Citation[]; className?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!items || items.length === 0) return null;
  return (
    <div className={cx("min-w-0", className)}>
      <Label as="p" className="mb-1">
        Grounded in the knowledge library
      </Label>
      <ol className="flex flex-col">
        {items.map((c, i) => (
          <li key={`${c.source}-${i}`} className="min-w-0 border-t border-line first:border-t-0">
            <button
              type="button"
              onClick={() => setOpen(open === i ? null : i)}
              aria-expanded={c.snippet ? open === i : undefined}
              disabled={!c.snippet}
              className="flex min-h-10 w-full min-w-0 items-center gap-3 py-2 text-left text-small text-fg transition-colors enabled:hover:text-accent disabled:cursor-default"
            >
              <span className="font-mono text-micro text-fg-faint">[{i + 1}]</span>
              <span className="min-w-0 flex-1 break-words">{c.source}</span>
              <span
                title={
                  c.library === "evolus"
                    ? "Cited by the Evolus knowledge library"
                    : "Retrieved by Atelier from the same brand documents (Brand workspace) and given to the model"
                }
              >
                <Badge tone={c.library === "evolus" ? "ok" : "faint"}>
                  {c.library === "evolus" ? "Evolus library" : "Library doc"}
                </Badge>
              </span>
            </button>
            {open === i && c.snippet && (
              <p className="mb-3 ml-8 rounded-panel bg-paper-2/70 px-4 py-3 text-small leading-relaxed text-fg-muted">
                {c.snippet}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
