import { useCurrentFrame } from "remotion";
import { scene, wordAt } from "../timing";

/** Local frame and a word lookup relative to the scene's start. */
export const useScene = (id: string) => {
  const s = scene(id);
  const f = useCurrentFrame();
  const rel = (w: string, n = 0) => wordAt(id, w, n) - s.from;
  return { s, f, rel };
};
export const eur = (n: number) => `€${n.toLocaleString("en-GB", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
