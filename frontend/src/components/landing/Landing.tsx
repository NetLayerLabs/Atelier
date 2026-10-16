"use client";

import { Agents } from "./Agents";
import { Architecture } from "./Architecture";
import { Hero } from "./Hero";
import { HowItWorks } from "./HowItWorks";
import { HumanAI } from "./HumanAI";
import { Problem } from "./Problem";
import { ClosingCta, Value } from "./Value";

/** The landing above the studio: what Atelier is, in about a minute of scrolling, then a hand-off to chapter I. */
export function Landing() {
  return (
    <div data-demo="landing">
      <Hero />
      <Problem />
      <HowItWorks />
      <Agents />
      <HumanAI />
      <Architecture />
      <Value />
      <ClosingCta />
    </div>
  );
}
