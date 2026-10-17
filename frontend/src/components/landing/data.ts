// Static copy for the landing. It describes what the product does; it never shows invented output. Model names,
// GPUs and connection states are read from GET /api/health at runtime (see Architecture / StatusStrip).
// Cited figures come only from docs/BUSINESS_VALUE.md, each with its source shown next to it.

export const CHAPTERS = [
  {
    numeral: "I",
    title: "The signal",
    short: "Signal",
    kicker: "Trend ingestion",
    human: "Drops in a mood board: a preset, uploaded images or image links.",
    agent:
      "A vision-language model names the trend, reads its silhouettes, palette and fabrics, and scores commercial viability.",
    artifact: "A structured trend read",
  },
  {
    numeral: "II",
    title: "The design",
    short: "Design",
    kicker: "Generative ideation",
    human: "Uploads their own sketch or photo - or asks for four concepts when a diffusion server is connected.",
    agent: "Reads the sketch with Gemma 4 on AMD (collar, closure, details) into the tech-pack brief; renders concepts on the diffusion server when one is connected.",
    artifact: "The designer's sketch, read into a brief - or four seeded concept renders",
  },
  {
    numeral: "III",
    title: "The vibe check",
    short: "Approve",
    kicker: "Human in the loop",
    human: "Picks a concept, directs it in plain words (typed or spoken) and approves one look.",
    agent:
      "Turns the brief into prompt, palette, silhouette and construction changes, reads them back, then renders four directed variations.",
    artifact: "An approved design with its direction",
  },
  {
    numeral: "IV",
    title: "Into production",
    short: "Pre-order → PO",
    kicker: "Agent pipeline",
    human: "Edits the tech pack if needed and can overrule the supplier pick.",
    agent: "Five agents run in sequence, from tech pack to purchase order, gated on real pre-order demand.",
    artifact: "Tech pack PDF, RFQs, extracted quotes, a live pre-order page, a forecast, a purchase order",
  },
] as const;

export type AgentInfo = {
  n: string;
  name: string;
  input: string;
  output: string;
  /** An optional second line under the output (the hand-off rule, etc.). */
  note?: string;
  engine: string;
  /** health service names behind this agent */
  services: string[];
};

export const AGENTS: AgentInfo[] = [
  {
    n: "01",
    name: "Tech pack",
    input: "The approved design, its trend read and the creative direction",
    output:
      "Bill of materials, measurements, construction notes, colourway, costing and retail price, validated against a schema",
    engine: "An Evolus agent on the AMD-hosted open model (Gemma 4), grounded in the brand book",
    services: ["evolus_agent"],
  },
  {
    n: "02",
    name: "Supplier outreach",
    input: "The tech pack and the target sourcing region",
    output:
      "Request-for-quote emails to the brand's own suppliers, each in the supplier's language (English kept alongside), with the exact colours to lab-dip against",
    engine: "The agent drafts; an Evolus workflow sends them to the brand's suppliers (or a pilot inbox)",
    services: ["evolus_outreach"],
  },
  {
    n: "03",
    name: "Supplier quotes",
    input: "The mills' quote documents (PDF or image), uploaded or emailed back",
    output:
      "A scored shortlist (price 45%, MOQ fit 30%, lead time 25%; a criterion the quote doesn't state is left out, never guessed) and a recommendation",
    note: "If the pick breaks a brand guardrail (margin floor, cost cap, lead time, MOQ, certificates), the agent stops and hands the call to you: approve, switch, or negotiate in the mill's language.",
    engine: "An Evolus document extractor reads each document; deterministic scoring; the agent writes the rationale",
    services: ["evolus_extractor"],
  },
  {
    n: "04",
    name: "Shopify pre-order",
    input: "The final render, title, copy and retail price",
    output: "A real product on a Shopify store, with a QR code to pre-order it",
    engine: "Shopify Admin API, or an Evolus workflow",
    services: ["shopify"],
  },
  {
    n: "05",
    name: "Pre-order demand → PO",
    input: "Real Shopify orders and the threshold (run size or supplier MOQ, or a configured stage threshold)",
    output:
      "An explained forecast of how many to make; once the threshold clears, a numbered purchase order sent to the mill through Evolus (without Evolus it stays a draft)",
    engine: "Atelier orchestrator; the forecast is closed-form statistics, no language model",
    services: ["shopify", "evolus_po"],
  },
];

export type CitedFigure = {
  /** The figure as printed (exactly as in the source). */
  value: string;
  unit?: string;
  label: string;
  source: string;
  href: string;
};

/** The problem, in cited figures (docs/BUSINESS_VALUE.md › "Use these"). */
export const PROBLEM_FIGURES: CitedFigure[] = [
  {
    value: "2.5–5",
    unit: "bn items",
    label: "items of excess stock produced in 2023, worth {USD}70–140 bn in sales",
    source: "McKinsey & BoF, The State of Fashion 2025",
    href: "https://www.businessoffashion.com/articles/retail/the-state-of-fashion-2025-report-inventory-excess-stock-supply-chain/",
  },
  {
    value: "4–9%",
    label: "of textile products put on the market in Europe are destroyed before use",
    source: "European Environment Agency, March 2024",
    href: "https://www.eea.europa.eu/en/newsroom/news/many-returned-and-unsold-textiles",
  },
  {
    value: "19 Jul 2026",
    label: "large companies may no longer destroy unsold apparel and footwear in the EU (ESPR, Art. 25)",
    source: "Regulation (EU) 2024/1781, via HLC",
    href: "https://hlc.com/en/publications/stop-the-destruction-of-textiles-how-compliance-changes-from-19-july-2026",
  },
];

/** The time baseline Atelier is measured against (Value section). */
export const DEV_TIME = {
  source: "McKinsey, Faster fashion (2018), via Retail Dive",
  href: "https://www.retaildive.com/news/Apparel-lead-times-McKinsey-vertical-integration/540838/",
};

/** Proof that selling first works (Value section). */
export const PREORDER_PROOF = [
  {
    source: "Business of Fashion (Stòffa)",
    href: "https://www.businessoffashion.com/articles/retail/zero-inventory-fashion-business/",
  },
  {
    source: "Glossy (Prabal Gurung, Antonio Berardi)",
    href: "https://www.glossy.co/fashion/pre-order-is-catching-on-as-a-solution-to-fashions-overproduction-problem/",
  },
];
