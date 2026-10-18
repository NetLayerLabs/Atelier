// Sound effects via ElevenLabs /v1/sound-generation. Skips files that already exist.
//   node scripts/sfx.mjs                 all missing
//   ONLY=stamp,impact node scripts/sfx.mjs   force regenerate some
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { ROOT, post, retry } from "./env.mjs";

const SFX = {
  scratch: ["Short comic vinyl record scratch, single, dry, funny stop", 0.8],
  sewing: ["Short burst of an electric sewing machine stitching fast, close, mechanical, no music", 1.6],
  snip: ["Single crisp sharp fabric scissors snip, close, dry", 0.5],
  tick: ["Single crisp clock tick, close, dry, short", 0.5],
  whoosh: ["Soft fast airy whoosh like fabric swishing past, smooth transition, no music", 1.0],
  swoosh_up: ["Quick rising digital swoosh, bright and clean, UI transition, no music", 0.9],
  click: ["Soft modern UI click, single, clean, short", 0.5],
  pop: ["Soft bubbly UI pop, single, clean, short, playful", 0.5],
  typing: ["Fast soft keyboard typing on a laptop, close, dry, a few seconds, no music", 2.5],
  paper: ["Quick paper sheets shuffle and slide on a desk, crisp, dry, short", 1.0],
  riser: ["Tension riser, rising airy synth swell building to a peak, cinematic, no drums", 3.5],
  impact: ["Deep clean cinematic impact with a warm sub tail, modern, single hit", 2],
  buzzer: ["Short comic game-show wrong-answer buzzer, two low tones, playful, dry", 0.9],
  chime: ["Bright clean confirmation chime, two soft ascending notes, modern, short tail", 1.5],
  register: ["Vintage cash register ka-ching with a bell, single, crisp, playful", 1.2],
  stamp: ["Firm rubber stamp hit on paper, single, close, dry", 0.6],
};

const dir = join(ROOT, "public/audio/sfx");
mkdirSync(dir, { recursive: true });
const only = process.env.ONLY ? process.env.ONLY.split(",") : null;

for (const [name, [text, dur]] of Object.entries(SFX)) {
  const f = join(dir, `${name}.mp3`);
  if (only ? !only.includes(name) : existsSync(f)) { console.log(`${name}: skip`); continue; }
  try {
    const buf = await retry(async () => {
      const res = await post("/sound-generation?output_format=mp3_44100_128", { text, duration_seconds: dur, prompt_influence: 0.5 });
      return Buffer.from(await res.arrayBuffer());
    });
    writeFileSync(f, buf);
    console.log(`${name}: ${(buf.length / 1024).toFixed(0)}kb`);
  } catch (e) { console.error(`${name}: FAILED ${e.message}`); }
}
