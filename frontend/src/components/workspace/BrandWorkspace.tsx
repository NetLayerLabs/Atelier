"use client";

import { MotionConfig } from "framer-motion";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  cx,
  Em,
  Eyebrow,
  IconArrowLeft,
  IconArrowRight,
  IconArrowUpRight,
  IconCheck,
  IconRefresh,
  InlineAlert,
  LinkButton,
  Ring,
  SectionHeading,
  Skeleton,
  SkeletonText,
  Stepper,
  type StepperStep,
} from "@/components/ds";
import { errorMessage } from "@/lib/api";
import { getWorkspace, type SectionKey, type SectionStatus, type Workspace } from "@/lib/workspace";
import { Header } from "../Header";
import { BrandBookStep, GuardrailsStep, PricesStep, ProfileStep, SalesStep, SuppliersStep } from "./steps";

const STEPS: { key: SectionKey; numeral: string; label: string }[] = [
  { key: "profile", numeral: "I", label: "Brand profile" },
  { key: "brand_book", numeral: "II", label: "Brand book" },
  { key: "suppliers", numeral: "III", label: "Suppliers" },
  { key: "prices", numeral: "IV", label: "Price list" },
  { key: "guardrails", numeral: "V", label: "Guardrails" },
  { key: "sales", numeral: "VI", label: "Sales history" },
];

function stepFromHash(): SectionKey {
  if (typeof window === "undefined") return "profile";
  const h = window.location.hash.replace("#", "");
  return (STEPS.find((s) => s.key === h)?.key ?? "profile") as SectionKey;
}

/** v5: onboarding for the brand's own data. Reached from the header ("Brand workspace"). */
export function BrandWorkspace() {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<SectionKey>("profile");
  const router = useRouter();

  const reload = useCallback(() => {
    getWorkspace()
      .then((w) => {
        setWs(w);
        setError(null);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    reload();
    const sync = () => setStep(stepFromHash());
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [reload]);

  const go = (k: SectionKey) => {
    setStep(k);
    window.history.replaceState(null, "", `#${k}`);
    window.scrollTo({ top: 0 });
  };

  const sections = Object.fromEntries((ws?.status.sections ?? []).map((s) => [s.key, s])) as Partial<
    Record<SectionKey, SectionStatus>
  >;
  const total = ws?.status.sections.length ?? STEPS.length;
  const done = ws?.status.sections.filter((s) => s.done).length ?? 0;

  return (
    <MotionConfig reducedMotion="user">
      <Header onStartOver={() => router.push("/")} />
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-12 pb-24 sm:px-8 sm:pt-16 lg:px-12">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_25rem] lg:items-end lg:gap-12">
          <SectionHeading
            as="h1"
            size="l"
            eyebrow={<Eyebrow tone={ws ? (ws.status.ready ? "ok" : "warn") : "faint"}>Brand workspace</Eyebrow>}
            title={
              ws?.profile?.name ? (
                ws.profile.name
              ) : (
                <>
                  Set up your <Em>brand</Em>
                </>
              )
            }
            lede="Everything Atelier knows about your brand comes from here: your profile, brand book, suppliers, prices and limits. Nothing is invented - what you leave empty stays empty."
          />
          {ws ? (
            <Card pad="md" role="status" className="flex items-center gap-5">
              <Ring
                value={total > 0 ? done / total : null}
                label="Workspace readiness"
                size={112}
                tone={ws.status.ready ? "ok" : "accent"}
                display={`${done}/${total}`}
                caption="sections"
              />
              <div className="min-w-0">
                {ws.status.ready ? (
                  <>
                    <p className="flex items-center gap-1.5 text-body font-medium text-ok">
                      <IconCheck size={16} strokeWidth={2.4} /> Ready
                    </p>
                    <p className="mt-1 text-small text-fg-muted">
                      The studio can approve designs and email your suppliers.
                    </p>
                    <LinkButton
                      href="/"
                      size="sm"
                      variant="secondary"
                      className="mt-3"
                      trailing={<IconArrowUpRight size={14} />}
                    >
                      Open the studio
                    </LinkButton>
                  </>
                ) : (
                  <>
                    <p className="text-body font-medium text-warn">Approving is blocked</p>
                    <p className="mt-1 text-small text-fg-muted">Still needed:</p>
                    <ul className="mt-1 flex flex-col gap-0.5 text-small text-fg">
                      {ws.status.missing.map((m) => (
                        <li key={m} className="flex gap-2">
                          <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-warn" />
                          {m}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </Card>
          ) : (
            !error && <Skeleton className="h-36 w-full rounded-card" />
          )}
        </div>

        {error && (
          <InlineAlert
            tone="bad"
            title="Couldn't load the workspace"
            className="mt-10"
            action={
              <Button size="sm" variant="secondary" icon={<IconRefresh size={14} />} onClick={reload}>
                Retry
              </Button>
            }
          >
            {error}
          </InlineAlert>
        )}
        {!ws && !error && (
          <div className="mt-12 flex flex-col gap-4" aria-label="Loading the workspace">
            <Skeleton className="h-11 w-full max-w-3xl rounded-full" />
            <Skeleton className="h-80 w-full rounded-card" />
            <SkeletonText lines={2} />
          </div>
        )}

        {ws && (
          <>
            <WorkspaceSteps step={step} sections={sections} go={go} className="mt-12 sm:mt-16" />
            <Card as="section" pad="lg" className="mt-4 min-w-0" aria-live="polite">
              {step === "profile" && <ProfileStep key={ws.profile?.updatedAt ?? "none"} ws={ws} reload={reload} />}
              {step === "brand_book" && <BrandBookStep ws={ws} reload={reload} />}
              {step === "suppliers" && <SuppliersStep ws={ws} reload={reload} />}
              {step === "prices" && <PricesStep ws={ws} reload={reload} />}
              {step === "guardrails" && <GuardrailsStep ws={ws} reload={reload} />}
              {step === "sales" && <SalesStep ws={ws} reload={reload} />}
              <StepFooter step={step} go={go} />
            </Card>
          </>
        )}
      </main>
    </MotionConfig>
  );
}

/**
 * The six workspace steps on the ds Stepper. Unlike the chapter stepper every step is reachable (the sections are
 * independent); each shows done (check), required-and-missing (amber dot) or optional, and the current step's
 * status line underneath.
 */
function WorkspaceSteps({
  step,
  sections,
  go,
  className,
}: {
  step: SectionKey;
  sections: Partial<Record<SectionKey, SectionStatus>>;
  go: (k: SectionKey) => void;
  className?: string;
}) {
  const st = sections[step];
  return (
    <div className={className}>
      <Stepper
        label="Workspace steps"
        variant="well"
        reachable="all"
        onSelect={(id) => go(id as SectionKey)}
        steps={STEPS.map((s) => {
          const sec = sections[s.key];
          return {
            id: s.key,
            label: s.label,
            numeral: s.numeral,
            status: s.key === step ? "current" : sec?.done ? "done" : "upcoming",
            marker:
              sec && !sec.done && sec.required ? (
                <span aria-hidden className="size-1.5 rounded-full bg-warn" />
              ) : undefined,
            srStatus: sec ? (sec.done ? " - done" : sec.required ? " - required" : " - optional") : undefined,
          } satisfies StepperStep;
        })}
      />
      {st && (
        <p className="mt-3 px-1 text-micro text-fg-muted">
          <span className={cx("font-medium", st.done ? "text-ok" : st.required ? "text-warn" : "text-fg-faint")}>
            {st.done ? "Done" : st.required ? "Required" : "Optional"}
          </span>
          {st.detail && !/^optional\b/i.test(st.detail) && ` · ${st.detail}`}
          {st.detail && /^optional\b/i.test(st.detail) && ` · ${st.detail.replace(/^optional\s*·\s*/i, "")}`}
        </p>
      )}
    </div>
  );
}

function StepFooter({ step, go }: { step: SectionKey; go: (k: SectionKey) => void }) {
  const i = STEPS.findIndex((s) => s.key === step);
  const next = STEPS[i + 1];
  const prev = STEPS[i - 1];
  return (
    <div className="mt-14 flex items-center justify-between gap-3 border-t border-line pt-6">
      {prev ? (
        <Button variant="ghost" size="sm" icon={<IconArrowLeft size={14} />} onClick={() => go(prev.key)}>
          {prev.label}
        </Button>
      ) : (
        <span />
      )}
      <span className="hidden text-micro text-fg-faint tabular sm:inline">
        Step {i + 1} of {STEPS.length}
      </span>
      {next ? (
        <Button variant="secondary" size="sm" trailing={<IconArrowRight size={14} />} onClick={() => go(next.key)}>
          {next.label}
        </Button>
      ) : (
        <span />
      )}
    </div>
  );
}
