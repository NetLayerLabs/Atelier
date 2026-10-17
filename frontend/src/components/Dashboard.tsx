"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useAtelier } from "@/lib/store";
import { BackendBanner } from "./BackendBanner";
import { CustomerVoice } from "./CustomerVoice";
import { DemoController } from "./DemoController";
import { IdeationStage } from "./Designs";
import { Button, IconArrowRight, IconRefresh } from "./ds";
import { Header } from "./Header";
import { Landing } from "./landing/Landing";
import { PipelineStage } from "./PipelineStage";
import { SiteFooter } from "./SiteFooter";
import { TrendAnalysisView } from "./TrendAnalysisView";
import { AnalysisError, Analysing, TrendInput } from "./TrendStage";
import { Chapter, scrollToId } from "./ui";
import { VibeStage } from "./VibeStage";

/** Scroll to a chapter once it has mounted. */
function useScrollOn(condition: boolean, id: string) {
  const prev = useRef(condition);
  useEffect(() => {
    if (condition && !prev.current) {
      const t = setTimeout(() => scrollToId(id), 120);
      prev.current = condition;
      return () => clearTimeout(t);
    }
    prev.current = condition;
  }, [condition, id]);
}

export function Dashboard() {
  const analyze = useAtelier((s) => s.analyze);
  const analyzeInput = useAtelier((s) => s.analyzeInput);
  const analyzePreviews = useAtelier((s) => s.analyzePreviews);
  const trend = useAtelier((s) => s.trend);
  const generate = useAtelier((s) => s.generate);
  const selectedId = useAtelier((s) => s.selectedId);
  const approve = useAtelier((s) => s.approve);
  const run = useAtelier((s) => s.run);
  const retryAnalyze = useAtelier((s) => s.retryAnalyze);
  const runGenerate = useAtelier((s) => s.runGenerate);
  const collectionGen = useAtelier((s) => s.collectionGen);
  const ideationMode = useAtelier((s) => s.ideationMode);
  const runCollection = useAtelier((s) => s.runCollection);
  const reset = useAtelier((s) => s.reset);

  const [chooseAnother, setChooseAnother] = useState(false);

  const sketchOpen = useAtelier((s) => s.sketchOpen);
  const openSketch = useAtelier((s) => s.openSketch);
  const showIdeation = generate.status !== "idle" || collectionGen.status !== "idle" || sketchOpen;
  const showVibe = !!selectedId;
  const showProduction = approve.status === "loading" || approve.status === "done" || !!run;

  useScrollOn(analyze.status === "done", "chapter-trend");
  useScrollOn(generate.status === "loading" || collectionGen.status === "loading" || sketchOpen, "chapter-ideation");
  useScrollOn(showVibe, "chapter-vibe");
  useScrollOn(approve.status === "done", "chapter-production");

  const startOver = () => {
    reset();
    setChooseAnother(false);
    window.scrollTo({ top: 0 });
  };

  return (
    <MotionConfig reducedMotion="user">
      <Header onStartOver={startOver} />
      <BackendBanner />
      <DemoController />


      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 sm:px-8 lg:px-12">
        <Landing />

        <Chapter id="chapter-trend" numeral="I" kicker="Trend ingestion" title="The signal">
          {analyze.status === "loading" ? (
            <Analysing input={analyzeInput} previewUrls={analyzePreviews} />
          ) : analyze.status === "done" && trend && !chooseAnother ? (
            <div>
              <TrendAnalysisView trend={trend} />
              <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                {!showIdeation && (
                  <>
                    <Button
                      onClick={runGenerate}
                      size="lg"
                      data-demo="generate"
                      trailing={<IconArrowRight size={16} />}
                      trailingBadge
                    >
                      Generate four concepts
                    </Button>
                    <Button variant="secondary" size="lg" onClick={openSketch} data-demo="sketch">
                      Start from my sketch
                    </Button>
                    <Button variant="ghost" size="lg" onClick={() => runCollection(4)}>
                      Compose a collection
                    </Button>
                  </>
                )}
                <Button variant="ghost" icon={<IconRefresh size={15} />} onClick={() => setChooseAnother(true)}>
                  Read a different trend
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              {analyze.status === "error" && (
                <AnalysisError message={analyze.error} hint={analyze.hint} onRetry={retryAnalyze} />
              )}
              {chooseAnother && trend && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel bg-paper-2 px-4 py-3 text-small text-fg-muted sm:px-5">
                  <span>Choosing a new source starts a fresh session.</span>
                  <Button variant="ghost" size="sm" onClick={() => setChooseAnother(false)}>
                    Cancel
                  </Button>
                </div>
              )}
              <TrendInputWithReset onStart={() => setChooseAnother(false)} />
            </div>
          )}
          {analyze.status !== "loading" && <CustomerVoice />}
        </Chapter>

        {showIdeation && (
          <Chapter
            id="chapter-ideation"
            numeral="II"
            kicker="Generative ideation"
            title={
              ideationMode === "collection"
                ? "The collection"
                : generate.status === "idle" && sketchOpen
                  ? "Your design"
                  : "Four concepts"
            }
          >
            <IdeationStage />
          </Chapter>
        )}

        {showVibe && (
          <Chapter id="chapter-vibe" numeral="III" kicker="Human in the loop" title="The vibe check">
            <VibeStage />
          </Chapter>
        )}

        {showProduction && (
          <Chapter id="chapter-production" numeral="IV" kicker="Agent pipeline" title="Into production">
            <PipelineStage />
            {run && run.status !== "running" && (
              <div className="mt-16 flex justify-center">
                <Button variant="secondary" onClick={startOver}>
                  Start a new collection
                </Button>
              </div>
            )}
          </Chapter>
        )}
      </main>

      <SiteFooter />
    </MotionConfig>
  );
}

/** Wraps TrendInput so starting a new analysis closes the "choose another" view. */
function TrendInputWithReset({ onStart }: { onStart: () => void }) {
  const status = useAtelier((s) => s.analyze.status);
  const prev = useRef(status);
  useEffect(() => {
    if (status === "loading" && prev.current !== "loading") onStart();
    prev.current = status;
  }, [status, onStart]);
  return <TrendInput />;
}
