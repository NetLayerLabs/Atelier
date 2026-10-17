"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Fragment, useState } from "react";
import { AUTH_REQUIRED_EVENT } from "@/lib/api";
import { useAtelier } from "@/lib/store";
import { DesignCard, SkeletonGrid } from "./Designs";
import { AtelierThinking, AtelierTurn, DirectInput, DirectorBubble, HeardCard } from "./Direction";
import {
  Badge,
  Button,
  Card,
  Disclosure,
  Em,
  Eyebrow,
  Field,
  GarmentTag,
  IconArrowDown,
  IconArrowUpRight,
  IconCheck,
  InlineAlert,
  Input,
  Label,
  LinkButton,
  NotConnected,
} from "./ds";
import { EASE } from "./ds/tokens";
import { ErrorNotice, scrollToId, SmartImage } from "./ui";
import { useWorkspaceStatus } from "./workspace/WorkspaceGate";
import { useAdminAuth } from "./AdminLogin";

export function VibeStage() {
  const selectedId = useAtelier((s) => s.selectedId);
  const designs = useAtelier((s) => s.designs);
  const labels = useAtelier((s) => s.labels);
  const rounds = useAtelier((s) => s.rounds);
  const refine = useAtelier((s) => s.refine);
  const direct = useAtelier((s) => s.direct);
  const directions = useAtelier((s) => s.directions);
  const collections = useAtelier((s) => s.collections);
  const approve = useAtelier((s) => s.approve);
  const locked = useAtelier((s) => !!s.runId || s.approve.status === "loading");
  const select = useAtelier((s) => s.select);
  const runRefine = useAtelier((s) => s.runRefine);
  const runDirect = useAtelier((s) => s.runDirect);
  const runApprove = useAtelier((s) => s.runApprove);
  const auth = useAdminAuth(); // hosted demo: visitors can try everything up to here

  const [qty, setQty] = useState("300");
  const workspace = useWorkspaceStatus(); // v5: approve needs the brand's own data first

  if (!selectedId || !designs[selectedId]) return null;
  const design = designs[selectedId];
  const label = labels[design.id];
  const parent = design.parentDesignId ? designs[design.parentDesignId] : undefined;
  const exchanges = rounds.filter((r) => r.kind === "refine" || r.kind === "direct");
  const latestRoundId = exchanges.at(-1)?.id;
  const variationRounds = exchanges.slice().reverse();
  const collection = design.collectionId ? collections[design.collectionId] : undefined;
  const direction = design.directionId ? directions[design.directionId] : undefined;
  const qtyNum = Number(qty);
  const qtyValid = Number.isInteger(qtyNum) && qtyNum >= 1 && qtyNum <= 100_000;
  const pending = direct.status === "loading" || refine.status === "loading";
  const gateOpen = !locked && !!workspace && !workspace.ready;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* The selected look */}
        <Card pad="sm" className="lg:sticky lg:top-36">
          <AnimatePresence mode="wait">
            <motion.div
              key={design.id}
              initial={{ opacity: 0, scale: 0.985 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: EASE }}
            >
              <SmartImage src={design.imageUrl} alt={`Concept No. ${label}`} className="aspect-[3/4] rounded-panel" />
            </motion.div>
          </AnimatePresence>
          <div className="px-2 pt-4 pb-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <GarmentTag tone="ink" code={design.garmentType}>
                Look {label}
              </GarmentTag>
              <span className="font-mono text-micro text-fg-faint tabular">seed {design.seed}</span>
            </div>
            {collection && (
              <p className="mt-3 text-small text-fg-muted">
                From the collection <span className="font-medium text-fg">{collection.name}</span>
              </p>
            )}
            {parent && (
              <p className="mt-2 text-small text-fg-muted">
                {direction ? "Directed" : "Refined"} from{" "}
                <button
                  type="button"
                  onClick={() => select(parent.id)}
                  disabled={locked}
                  className="font-medium text-fg underline decoration-line-bold underline-offset-4 hover:decoration-fg disabled:no-underline"
                >
                  Look {labels[parent.id]}
                </button>
                {design.vibe && (
                  <>
                    {" "}
                    · <span className="text-fg">“{design.vibe}”</span>
                  </>
                )}
              </p>
            )}
            <Disclosure
              variant="row"
              className="mt-3 border-b-0 border-t border-line"
              title={<span className="text-small">Diffusion prompt</span>}
            >
              <p className="font-mono text-micro leading-relaxed break-words text-fg-muted">{design.prompt}</p>
            </Disclosure>
          </div>
        </Card>

        {/* The conversation: your brief, Atelier's read-back, then the composer */}
        <Card pad="none" as="section" aria-label={`Creative direction for Look ${label}`} className="flex flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
            <div className="min-w-0">
              <Eyebrow tone={pending ? "accent" : "neutral"} live={pending}>
                Creative direction
              </Eyebrow>
              <p className="mt-1 truncate text-title text-fg">Directing Look {label}</p>
            </div>
            {exchanges.length > 0 && (
              <Badge tone="neutral">
                {exchanges.length} {exchanges.length === 1 ? "brief" : "briefs"}
              </Badge>
            )}
          </header>

          <div className="flex flex-col gap-5 px-4 py-6 sm:px-6" aria-live="polite">
            <AtelierTurn>
              <div className="rounded-[24px] rounded-bl-lg bg-paper-2 px-4 py-3 text-body text-fg">
                How should Look {label} change? Brief it the way you would a studio - colour, length, references. I&rsquo;ll
                read it back before I render anything.
              </div>
            </AtelierTurn>

            {exchanges.map((r) => {
              const d = r.directionId ? directions[r.directionId] : undefined;
              const from = r.parentDesignId ? labels[r.parentDesignId] : undefined;
              return (
                <Fragment key={r.id}>
                  <DirectorBubble meta={from ? `to Look ${from}` : undefined}>
                    {d?.instruction ?? r.vibe ?? "-"}
                  </DirectorBubble>
                  <AtelierTurn>
                    <div data-demo={r.id === latestRoundId && d ? "heard" : undefined}>
                      {d ? (
                        <HeardCard direction={d} parentLabel={from} />
                      ) : (
                        <div className="rounded-[24px] rounded-bl-lg bg-paper-2 px-4 py-3 text-body text-fg">
                          Refined Look {from ?? "-"} into {r.designIds.length} variations.
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => scrollToId(`variations-${r.id}`)}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-micro text-fg-muted hover:bg-paper-2 hover:text-fg"
                      >
                        <IconArrowDown size={12} />
                        {r.designIds.length} variations below
                      </button>
                    </div>
                  </AtelierTurn>
                </Fragment>
              );
            })}

            {direct.status === "loading" && direct.instruction && (
              <>
                <DirectorBubble>{direct.instruction}</DirectorBubble>
                <AtelierThinking label={label} />
              </>
            )}
            {refine.status === "loading" && refine.vibe && (
              <>
                <DirectorBubble>{refine.vibe}</DirectorBubble>
                <AtelierThinking label={label} />
              </>
            )}
            {direct.status === "error" && (
              <>
                {direct.instruction && <DirectorBubble>{direct.instruction}</DirectorBubble>}
                <AtelierTurn>
                  {direct.hint ? (
                    <NotConnected
                      compact
                      service="Brain and diffusion model"
                      hint={direct.hint}
                      onRetry={() => direct.instruction && runDirect(direct.instruction)}
                    >
                      {direct.error ?? "Direction needs the brain to read it and the diffusion model to render it."}
                    </NotConnected>
                  ) : (
                    <ErrorNotice
                      title="Direction failed"
                      message={direct.error}
                      onRetry={() => direct.instruction && runDirect(direct.instruction)}
                    />
                  )}
                </AtelierTurn>
              </>
            )}
            {refine.status === "error" && (
              <AtelierTurn>
                {refine.hint ? (
                  <NotConnected compact service="Diffusion model" hint={refine.hint} onRetry={() => refine.vibe && runRefine(refine.vibe)}>
                    {refine.error}
                  </NotConnected>
                ) : (
                  <ErrorNotice title="Refinement failed" message={refine.error} onRetry={() => refine.vibe && runRefine(refine.vibe)} />
                )}
              </AtelierTurn>
            )}
          </div>

          <div className="mt-auto px-3 pt-2 pb-4 sm:px-5">
            <DirectInput label={label} />
          </div>
        </Card>
      </div>

      {/* Variations, newest first */}
      {(pending || variationRounds.length > 0) && (
        <div className="mt-12 flex flex-col gap-10">
          <div>
            <Eyebrow>Variations</Eyebrow>
            <p className="mt-2 text-title text-fg">Pick the strongest - it becomes the look you direct or approve.</p>
          </div>
          {pending && <SkeletonGrid label="Directing variations" />}
          {variationRounds.map((r) => {
            const d = r.directionId ? directions[r.directionId] : undefined;
            const from = r.parentDesignId ? labels[r.parentDesignId] : "-";
            return (
              <div key={r.id} id={`variations-${r.id}`} className="scroll-mt-40">
                <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
                  <Label>From Look {from}</Label>
                  <span className="min-w-0 text-body text-fg-muted">“{d?.instruction ?? r.vibe}”</span>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                  {r.designIds.map((id, i) => (
                    <DesignCard
                      key={id}
                      design={designs[id]}
                      label={labels[id]}
                      index={i}
                      selected={selectedId === id}
                      disabled={locked}
                      onSelect={() => {
                        select(id);
                        scrollToId("chapter-vibe");
                      }}
                      compact
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* The decision: Scenar's black card with one white pill */}
      <div className="mt-12 flex flex-col gap-3">
        <Card variant="inverse" pad="lg" data-demo="approve" className="overflow-hidden">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-end">
            <div className="min-w-0">
              <Eyebrow>Approve for production</Eyebrow>
              <p className="mt-4 text-display-m text-balance">
                Hand Look {label} to the agents, <Em accent>or keep directing.</Em>
              </p>
              <p className="mt-4 max-w-xl text-body text-fg-muted">
                They write the tech pack, brief your suppliers, and open a Shopify pre-order to validate demand before
                anything is sewn.
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <GarmentTag code={design.garmentType}>
                  Look {label}
                </GarmentTag>
                {direction && <span className="text-micro text-fg-faint">with your direction applied</span>}
              </div>
            </div>
            <div className="flex flex-col gap-4">
              <Field label="Production quantity" hint="Units for the RFQs; 1–100,000." error={!qtyValid ? "Enter a whole number between 1 and 100,000." : undefined}>
                <Input
                  id="qty"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={100000}
                  step={1}
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  disabled={locked}
                  suffix="units"
                  className="font-mono text-body-l"
                />
              </Field>
              <Button
                variant="primary"
                size="lg"
                data-demo="approve-button"
                onClick={() => runApprove(qtyNum)}
                disabled={!qtyValid || locked || workspace?.ready === false}
                loading={approve.status === "loading"}
                icon={locked && approve.status !== "loading" ? <IconCheck size={16} strokeWidth={2.4} /> : undefined}
                // Inside the inverse card the primary pill is re-pointed to white-on-black's opposite (ds-inverse).
                className="w-full"
              >
                {locked && approve.status !== "loading" ? "Approved" : "Approve for production"}
              </Button>
              {auth?.required && !auth.signedIn && !locked && (
                <p className="text-micro text-fg-muted">
                  Approving emails real suppliers and opens a real Shopify pre-order, so it needs the admin token.{" "}
                  <button
                    type="button"
                    className="underline underline-offset-2 hover:text-fg"
                    onClick={() => window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT))}
                  >
                    Sign in
                  </button>
                </p>
              )}
            </div>
          </div>
        </Card>
        {gateOpen && workspace && (
          <InlineAlert
            tone="warn"
            data-demo="workspace-gate"
            title="Set up the Brand workspace first"
            action={
              <LinkButton
                href="/workspace"
                target="_blank"
                rel="noopener"
                variant="secondary"
                size="sm"
                trailing={<IconArrowUpRight size={14} />}
              >
                Open Brand workspace
              </LinkButton>
            }
          >
            Approving sends RFQs to your real suppliers, so Atelier needs {workspace.missing.join("; ")}. It opens in a new
            tab; come back here once it&rsquo;s ready.
          </InlineAlert>
        )}
        {approve.status === "error" && (
          <ErrorNotice
            title="Approval failed"
            message={approve.error}
            hint={approve.hint}
            onRetry={() => runApprove(approve.quantity ?? qtyNum)}
          />
        )}
      </div>
    </div>
  );
}
