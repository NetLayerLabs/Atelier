"use client";

import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import type { CreativeDirection } from "@/lib/api";
import { useDemoCommand } from "@/lib/demo";
import { useSpeechDirection } from "@/lib/speech";
import { useAtelier } from "@/lib/store";
import {
  AtelierMark,
  Button,
  ChipButton,
  Chip,
  GarmentTag,
  IconArrowRight,
  IconNeedle,
  Label,
  Spinner,
  Stitch,
  Swatch,
} from "./ds";
import { cx, EASE } from "./ds/tokens";
import { RouteTag } from "./Inference";

/** Quick picks go through the same natural-language direction flow as typed or spoken input. */
const QUICK_PICKS = [
  "darker, cropped, more Margiela",
  "quieter, more minimal",
  "more avant-garde",
  "90s archival",
  "sustainable materials",
  "Rick Owens",
];

/** The backend's limit on a direction (DirectRequest.instruction). */
const MAX_DIRECTION = 500;

const MIC_TIP =
  "Speak your direction. Uses your browser’s built-in speech recognition, which may send audio to a cloud service (e.g. Google in Chrome).";

/**
 * The direction composer (the bottom of the conversation): a rounded field with a mic and the Direct button,
 * a character counter and quick picks. Keeps `data-demo="direction"` (wrapper), `#direction` (the field the tour
 * types into via the `direct-text` command) and `data-demo="direct-submit"`.
 */
export function DirectInput({ label }: { label: string }) {
  const direct = useAtelier((s) => s.direct);
  const locked = useAtelier((s) => !!s.runId || s.approve.status === "loading");
  const runDirect = useAtelier((s) => s.runDirect);
  const [text, setText] = useState("");
  const [tooLong, setTooLong] = useState<string | null>(null);
  const busy = direct.status === "loading";

  const submit = (value: string) => {
    if (!value.trim() || busy || locked) return;
    setText(value);
    if (value.trim().length > MAX_DIRECTION) {
      setTooLong(
        `That direction is ${value.trim().length} characters - keep it to ${MAX_DIRECTION} (a sentence or two works best).`,
      );
      return;
    }
    setTooLong(null);
    void runDirect(value.trim());
  };

  const speech = useSpeechDirection((heard) => submit(heard));
  // Demo mode types the direction into this field (typewriter), then presses Direct.
  useDemoCommand((c) => c.type === "direct-text" && setText(c.text));

  const count = (speech.listening ? speech.interim : text).trim().length;
  const over = count > MAX_DIRECTION;

  return (
    <div data-demo="direction" className="flex flex-col gap-3">
      <div className="flex gap-2 overflow-x-auto pb-1 ds-noscrollbar sm:flex-wrap sm:overflow-visible" aria-label="Quick directions">
        {QUICK_PICKS.map((chip) => (
          <ChipButton
            key={chip}
            size="sm"
            onClick={() => submit(chip)}
            disabled={busy || locked}
            selected={direct.instruction === chip && direct.status !== "idle"}
            className="disabled:opacity-50"
          >
            {chip}
          </ChipButton>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
        className={cx(
          "rounded-[26px] border bg-surface p-2 transition-[border-color,box-shadow] duration-200 focus-within:border-accent focus-within:ring-4 focus-within:ring-accent-soft",
          speech.listening ? "border-accent" : over ? "border-bad" : "border-line-bold",
          locked && "opacity-60",
        )}
      >
        <label htmlFor="direction" className="sr-only">
          Creative direction for Look {label}
        </label>
        <textarea
          id="direction"
          rows={2}
          value={speech.listening ? speech.interim : text}
          onChange={(e) => {
            setText(e.target.value);
            if (tooLong && e.target.value.trim().length <= MAX_DIRECTION) setTooLong(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit(text);
            }
          }}
          disabled={locked || speech.listening}
          readOnly={speech.listening}
          placeholder={speech.listening ? "Listening…" : `Brief Look ${label}… e.g. make it darker, cropped, more Margiela`}
          className="block w-full resize-none bg-transparent px-3 pt-2 text-body-l text-fg outline-none placeholder:text-fg-faint disabled:cursor-not-allowed"
          aria-describedby="direction-hint direction-count"
          aria-invalid={over || undefined}
        />
        <div className="flex items-center justify-between gap-2 pt-1 pl-3">
          <span
            id="direction-count"
            className={cx("font-mono text-micro tabular", over ? "text-bad" : "text-fg-faint")}
            aria-live={over ? "polite" : "off"}
          >
            {count}/{MAX_DIRECTION}
          </span>
          <div className="flex items-center gap-2">
            {speech.supported && (
              <button
                type="button"
                onClick={speech.listening ? speech.stop : speech.start}
                disabled={locked || busy}
                title={MIC_TIP}
                aria-label={speech.listening ? "Stop listening" : "Speak a direction"}
                aria-pressed={speech.listening}
                className={cx(
                  "relative grid size-10 place-items-center rounded-full transition-colors duration-200 disabled:opacity-40",
                  speech.listening ? "bg-accent text-on-accent" : "bg-paper-2 text-fg hover:bg-surface-muted",
                )}
              >
                {speech.listening && <span aria-hidden className="ds-live absolute inset-0 rounded-full ring-2 ring-accent/50" />}
                <MicIcon />
              </button>
            )}
            <Button
              type="submit"
              data-demo="direct-submit"
              loading={busy}
              disabled={!text.trim() || locked || speech.listening}
              trailing={<IconArrowRight size={15} />}
              trailingBadge
            >
              Direct it
            </Button>
          </div>
        </div>
      </form>
      {speech.listening && (
        <p className="flex items-center gap-2 text-small text-accent" aria-live="polite">
          <span aria-hidden className="ds-live size-1.5 rounded-full bg-accent" />
          Listening - say the direction, Atelier will act when you pause.
        </p>
      )}
      {speech.error && !speech.listening && <p className="text-small text-bad">{speech.error}</p>}
      {tooLong && (
        <p role="alert" className="text-small text-bad">
          {tooLong}
        </p>
      )}
      <p id="direction-hint" className="px-1 text-micro text-fg-faint">
        Type{speech.supported ? " or speak" : ""} it the way you’d brief a studio. Enter sends, Shift+Enter adds a line.
        Atelier reads it back, directs Look {label} into four variations, and carries the changes into the tech pack.
      </p>
    </div>
  );
}

function MicIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="relative size-4" fill="none" stroke="currentColor" strokeWidth="1.75">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" strokeLinecap="round" />
    </svg>
  );
}

// --------------------------------------------------------------------------- conversation pieces

/** The creative director's instruction: Scenar's black "you" bubble on the right, like a sent message. */
export function DirectorBubble({ children, meta }: { children: ReactNode; meta?: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
      className="flex flex-col items-end gap-1.5 pl-8 sm:pl-16"
    >
      <p className="max-w-full rounded-[24px] rounded-br-lg bg-inverse px-4 py-3 text-body break-words text-on-inverse sm:px-5 sm:py-3.5">
        {children}
      </p>
      {meta && <span className="pr-2 text-micro text-fg-faint">{meta}</span>}
    </motion.div>
  );
}

/** Atelier's side of the conversation: its mark beside a light card. */
export function AtelierTurn({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: EASE }}
      className={cx("flex items-end gap-2.5 pr-0 sm:pr-6", className)}
    >
      <span aria-hidden className="mb-1 grid size-8 shrink-0 place-items-center rounded-full bg-inverse text-on-inverse">
        <AtelierMark size={20} />
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </motion.div>
  );
}

/** Atelier is reading the direction (the brain, then the diffusion model). */
export function AtelierThinking({ label }: { label: string }) {
  return (
    <AtelierTurn>
      <div className="inline-flex items-center gap-2.5 rounded-[24px] rounded-bl-lg bg-paper-2 px-4 py-3 text-small text-fg-muted">
        <Spinner size={13} className="text-fg" />
        Reading your direction, then rendering four variations of Look {label}…
      </div>
    </AtelierTurn>
  );
}

function Row({ title, children, index }: { title: ReactNode; children: ReactNode; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.12 + index * 0.07, duration: 0.5, ease: EASE }}
      className="grid grid-cols-1 gap-2 border-t border-line py-3.5 sm:grid-cols-[8.5rem_minmax(0,1fr)] sm:gap-4"
    >
      <Label className="pt-1.5">{title}</Label>
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">{children}</div>
    </motion.div>
  );
}

function SwatchRow({ colors }: { colors: string[] }) {
  return (
    <span className="flex gap-1">
      {colors.map((c, i) => (
        <span key={`${c}-${i}`} title={c}>
          <Swatch color={c} size="sm" />
        </span>
      ))}
    </span>
  );
}

/**
 * "Atelier heard…" - the read-back: Atelier's interpretation of the brief as structured changes (prompt,
 * palette before → after, silhouette, fabrics, references as garment tags, tech pack notes). A light card on
 * Atelier's side of the conversation, with a stitched seam marking the hand-off from you to the agent.
 */
export function HeardCard({ direction, parentLabel }: { direction: CreativeDirection; parentLabel?: string }) {
  const d = direction;
  let g = 0;
  return (
    <div className="rounded-[24px] rounded-bl-lg border border-line bg-surface p-4 shadow-e2 sm:p-6">
      <Stitch label="You → agent" />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-small font-medium text-fg">
          Atelier heard{parentLabel ? <span className="font-normal text-fg-muted"> · directing Look {parentLabel}</span> : null}
        </p>
        <RouteTag route={d.generatedBy} />
      </div>
      <p className="mt-2 text-body text-fg-muted">{d.interpretation}</p>

      <div className="mt-4">
        {(d.promptAdditions.length > 0 || d.promptRemovals.length > 0) && (
          <Row title="Prompt" index={g++}>
            {d.promptAdditions.map((p) => (
              <span
                key={`+${p}`}
                className="inline-flex h-7 max-w-full items-center rounded-full bg-inverse px-3 text-micro font-medium text-on-inverse"
              >
                <span className="truncate">+ {p}</span>
              </span>
            ))}
            {d.promptRemovals.map((p) => (
              <span
                key={`-${p}`}
                className="inline-flex h-7 max-w-full items-center rounded-full border border-line-strong px-3 text-micro text-fg-faint line-through"
              >
                <span className="truncate">{p}</span>
              </span>
            ))}
          </Row>
        )}
        {d.paletteShift && (
          <Row title="Palette" index={g++}>
            <span className="flex flex-wrap items-center gap-2.5">
              <SwatchRow colors={d.paletteShift.before} />
              <IconArrowRight size={16} className="text-fg-faint" aria-hidden />
              <SwatchRow colors={d.paletteShift.after} />
            </span>
            <span className="w-full pt-1 text-micro text-fg-muted">{d.paletteShift.note}</span>
          </Row>
        )}
        {d.silhouetteChanges.length > 0 && (
          <Row title="Silhouette" index={g++}>
            {d.silhouetteChanges.map((s) => (
              <Chip key={s}>{s}</Chip>
            ))}
          </Row>
        )}
        {d.fabricsAfter && d.fabricsAfter.length > 0 && (
          <Row title="Fabrics" index={g++}>
            {d.fabricsAfter.map((f, i) => (
              <Chip key={f} variant={i === 0 ? "outline" : "soft"}>
                {f}
                {i === 0 && <span className="ml-1 text-fg-faint">· shell</span>}
              </Chip>
            ))}
          </Row>
        )}
        {d.references.length > 0 && (
          <Row title="References" index={g++}>
            {d.references.map((r) => {
              const [name, gloss] = r.split(/ [-\u2014] /);
              return (
                <span key={r} className="flex max-w-full items-center gap-2">
                  <GarmentTag>{name}</GarmentTag>
                  {gloss && <span className="min-w-0 text-micro text-fg-muted">{gloss}</span>}
                </span>
              );
            })}
          </Row>
        )}
        {d.techPackHints.length > 0 && (
          <Row title="Into the tech pack" index={g++}>
            <ul className="flex w-full flex-col gap-1.5">
              {d.techPackHints.map((h) => (
                <li key={h} className="flex gap-2.5 rounded-panel bg-paper-2 px-3 py-2 font-mono text-micro text-fg-muted">
                  <IconNeedle size={14} className="mt-px shrink-0 text-fg" aria-hidden />
                  <span className="min-w-0 break-words">{h}</span>
                </li>
              ))}
            </ul>
          </Row>
        )}
      </div>
    </div>
  );
}
