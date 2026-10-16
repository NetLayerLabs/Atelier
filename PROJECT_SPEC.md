# Atelier: The Autonomous Fashion & Merchandising Agent

**Target Event**: AMD Developer Hackathon: ACT III
**Goal**: 1st Place & Vibe Generation "Best Solution" Prize

## 1. The Core Concept
**Atelier** is an end-to-end AI agent that acts as a co-designer and autonomous supply chain manager for fashion brands. It solves the multi-billion dollar "dead stock" problem in retail by combining real-time trend analysis, generative design, and automated procurement.

## 2. Hackathon Alignment (Why this wins)
* **Evolus Business Agents Track**: It runs a complex, real-world business process end-to-end: Trend Identification -> Product Design -> Manufacturing Spec Generation -> Supplier Procurement -> eCommerce Launch.
* **Vibe Generation ("Best Solution" Criteria)**: This is the perfect embodiment of the "Human + AI creative workflow." The AI handles the brutal data crunching and supply-chain logistics, which elevates the human to the role of pure Creative Director. 
* **Hybrid (Commercial Value)**: Atelier reduces the trend-to-market timeline from 6 months to 24 hours and eliminates inventory risk by launching products as pre-orders. 

## 3. The Architecture (Powered by AMD)
To prove absolute technical mastery and win the hardware category, Atelier runs a massive multimodal trifecta on **AMD Developer Cloud** (using ROCm):
1. **Vision Model (e.g., LLaVA)**: Scrapes and ingests fashion week streams or social media videos to identify emerging micro-trends (silhouettes, colors, fabrics).
2. **Diffusion Model (e.g., Stable Diffusion / Flux)**: Generates high-fidelity garment concepts based on the extracted trends.
3. **LLM Orchestrator (e.g., Llama-3 70B via vLLM)**: Acts as the cognitive brain, parsing the human's feedback and driving the Evolus API.

## 4. The Agent Loop (Evolus Integration)
1. **Trend Ingestion**: The Vision model flags a rising trend (e.g., "oversized asymmetrical denim").
2. **Generative Ideation**: The Diffusion model generates 4 concept designs based on that trend.
3. **Human Approval**: The Human Creative Director views the concepts in the Atelier dashboard. They select their favorite design and tweak the "vibe" (e.g., "make it more avant-garde").
4. **Evolus Orchestration**: Once the human hits "Approve", the Evolus agent takes over:
   - **Generation**: The LLM writes a standard manufacturing "Tech Pack" (measurements, bill of materials).
   - **Automated Outreach**: An Evolus workflow drafts and queues emails to fabric suppliers in China/Italy requesting quotes based on the Tech Pack.
   - **MCP Connector**: The final high-res render is automatically pushed to the brand's Shopify store as a "Pre-Order" to instantly validate market demand before a single physical garment is sewn.

## 5. Next Steps for Building in Claude Code
This repository is the workspace. Here is the attack plan for the next 48 hours:
1. **Initialize the Project**: Set up a Next.js (TypeScript) or Python backend project.
2. **AMD Cloud Setup**: Spin up your AMD instance and get `vLLM` running with an open model (like Llama-3-8B or 70B) so you have an OpenAI-compatible endpoint.
3. **Evolus Integration**: Create your free workspace at `app.evolus.ai` and start writing the REST API calls to trigger the automated supplier emails and Shopify push.
4. **The UI**: Build a beautiful, slick "Creative Director Dashboard" where the human interacts with the generated designs.
