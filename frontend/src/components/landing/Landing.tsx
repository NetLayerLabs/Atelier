"use client";

import { useRef } from "react";
import { Agents } from "./Agents";
import { Architecture } from "./Architecture";
import { Hero } from "./Hero";
import { HowItWorks } from "./HowItWorks";
import { HumanAI } from "./HumanAI";
import { PageTape } from "./PageTape";
import { Problem } from "./Problem";
import { ClosingCta, Value } from "./Value";

/** The landing above the studio: what Atelier is, in about a minute of scrolling, then a hand-off to chapter I. */
export function Landing() {
  const root = useRef<HTMLDivElement>(null);
  return (
    <div ref={root} data-demo="landing">
      <Hero />
      <Problem />
      <HowItWorks />
      <Agents />
      <HumanAI />
      <Architecture />
      <Value />
      <ClosingCta />
      {/* xl+: the tape in the gutter that reads your progress through the sections (fixed; client-only) */}
      <PageTape rootRef={root} />
    </div>
  );
}
