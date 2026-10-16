// v6: honest model labels. Everything here is derived from what /api/health reports (the served model id and the
// GPU label) - a family name is only shown when the served id says so, never assumed.

/** The served id is a Gemma 4 checkpoint, e.g. "google/gemma-4-26B-A4B-it". */
export function isGemma4(model?: string): boolean {
  return !!model && model.toLowerCase().includes("gemma-4");
}

/**
 * "Gemma 4 (Google, open) on AMD Instinct" for a real (not fake) connected Gemma 4 endpoint whose GPU label is an
 * AMD Instinct; "Gemma 4 (Google, open)" when the GPU isn't reported as one; undefined for any other model or a fake.
 */
export function gemmaLabel(model?: string, gpu?: string, fake?: boolean): string | undefined {
  if (fake || !isGemma4(model)) return undefined;
  return gpu && /instinct/i.test(gpu) ? "Gemma 4 (Google, open) on AMD Instinct" : "Gemma 4 (Google, open)";
}
