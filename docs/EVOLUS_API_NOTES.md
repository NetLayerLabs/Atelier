# Evolus API notes (compiled 2026-10-13)

A working reference for what Atelier calls, with a source for every fact. We have no workspace key yet, so nothing
here has been tested against a real workspace.

**Source tags.** Each fact is tagged:

- **[docs]** VERIFIED on https://evolus.ai/en/developers (server-rendered, read in full including the code tabs).
- **[app]** VERIFIED in the Evolus web app's generated API client (`https://app.evolus.ai/main-*.js`) and its UI
  strings (`/i18n/en.json`). These are real endpoint templates and field names, but they are not in the public docs.
- **[probe]** VERIFIED by unauthenticated calls to `api.evolus.ai` (401 means the route exists).
- **[event]** VERIFIED on https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii,
  https://evolus.ai/en/hackathon or https://evolus.ai/en/hackathon-conditions.
- **[3p]** INFERRED from a third-party hackathon repository that uses the API
  (github.com/brainupgrade-in/compressor-maintenance-copilot).
- **[inferred]** Our inference, not seen anywhere.

The full OpenAPI spec is at `GET https://api.evolus.ai/api/v1/integrations/openapi`, but it needs a key
([app], [probe] → 401). Once we have a key, fetch it and update this file.

## Base URLs and auth

| Interface | Base | Auth | Tag |
|---|---|---|---|
| Agent chat (OpenAI-compatible) | `https://api.evolus.ai/v1` | `Authorization: Bearer <application API key>` | [docs] |
| REST API | `https://api.evolus.ai/api/v1` | `X-ApiKey` + `X-Application-Id`, or `X-User-ApiKey` | [docs] |
| MCP server | `https://api.evolus.ai/mcp` | `X-ApiKey` + `X-Application-Id`, or `X-User-ApiKey` (a Bearer token also works) | [docs], [probe] |

- **Keys and the space id.** Create an application key on the workspace's API keys page. The same page shows the
  "Space ID", which is the `X-Application-Id` value [docs][app]. Personal keys live under Profile → API keys and go
  in the `X-User-ApiKey` header [app].
- **Permissions.** Keys are either full access or granular, with scopes such as agents:chat, rag-documents,
  workflows:execute, ai-tools:use and webhooks. A call outside the key's scopes returns 403 [app].
- **Libraries may need a user key.** Library ("memories") calls might need a personal user key, because the app key
  got 401 in the third-party repo [3p]. Atelier sends `X-User-ApiKey` for library calls when `EVOLUS_USER_API_KEY`
  is set.
- **Error formats.** REST errors are RFC 7807 `{"title","status","errorCode","traceId"}`. `/v1` errors use the
  OpenAI shape `{"error":{"message","type","param"}}` [probe].
- **Limits.**
  - 60 requests per minute per workspace (429 when exceeded) [docs][event].
  - 50,000 platform credits per event workspace; 402 when they run out [event].
  - Calls to your own model are free of credits [docs].

## Agent chat (the brain)

### OpenAI-compatible endpoint [docs]

- `GET /v1/models` lists the agents. Each `id` is `applicationId:agentId`.
- `POST /v1/chat/completions` with `"model": "<applicationId>:<agentId>"`.
- Message content must be a text string.
- Parameters such as `temperature` "are not applied".
- `stream: true` returns SSE that ends with `data: [DONE]`.
- **Conversations.** Every response has an `X-Conversation-Id` header. Send it back to continue the
  conversation: Evolus then processes only your last user message. Without it, the messages you send are the
  context of a new conversation.
- **Errors.** A bad model string gives
  `400 {"error":{"message":"Invalid model format. Expected: {applicationId}:{agentId}"}}` [probe].
- **Citations.** None are documented on this endpoint [inferred: plain content].

### REST endpoint [app]

- `POST /api/v1/agents/{agentId}/ask` with `{content, conversationId?, skipChatHistory?, …}`.
- Returns `{agentId, answer, citations[{documentId, sourceUrl, startIndex, endIndex, textToReplace}], conversationId, totalTokenCount, …}`.
- Streaming variant: `POST …/ask-stream` (wire format not documented).

### How Atelier uses it

- `EVOLUS_AGENT_TRANSPORT=openai` is the default. `rest` returns the library citations as well.
- The agent's model is our AMD vLLM endpoint, connected under bring-your-own model (below).

## Bring your own model (AMD vLLM)

- Connect any OpenAI-compatible endpoint whose model supports function calling. In the UI: add the base URL, model
  name and API key, test the connection, then pick the model in your agent [docs].
- The docs' vLLM example:
  `vllm serve … --host 0.0.0.0 --port 8000 --api-key "$VLLM_API_KEY" --enable-auto-tool-choice --tool-call-parser hermes` [docs].
- Plain `http://` works only with an IP address; a domain name needs `https://` [app].
- The connection test checks a short answer, a tool call, a streamed answer and reasoning levels [app].
- In event spaces, agents, extractors and the AI blocks of workflows run only on your models. OCR, libraries and
  AI Tools run on Evolus models and use credits [app].
- **API equivalents** [app]:
  - `POST /api/v1/own-models/connections/test {apiBaseUrl, apiKey, modelId, presetKey}`
  - `POST /api/v1/own-models/connections`
  - `POST …/{id}/models {modelId, name, contextLength}`
- An agent's `modelKey` for your own model is `own/<name>` [3p].

## Knowledge libraries ("memories")

- **Upload a document** [docs]:
  - `POST /api/v1/memories/{libraryId}/documents?language=en` with multipart `file`.
  - Returns 201 and indexes in the background.
  - The default language is `it`, so always pass `language`.
- **Import a web page** [docs]: `POST …/documents/import-url {title, url}` (that page only, no crawling).
- **List documents** [docs]: `GET /api/v1/memories/{libraryId}/documents` returns
  `[{id, title, ingestionStatus, chunkCount, …}]` (field names from [app]).
- **Create a library** [app]: `POST /api/v1/memories/simple {name, type?, aiAccess?}` returns `{id, …}`.
- **Attach a library to an agent** [app]: `POST /api/v1/agents/{agentId}/memories {memoryId}`.
- **No standalone search endpoint.** `/memories/{id}/search` and `/query` return 404 [probe]. You query a library
  by asking an agent it is attached to; REST `/ask` returns the `citations` [app].
- **Atelier's approach.** We put retrieved passages from the same documents in the prompt and label them
  `library: "local"`. Platform citations are labelled `"evolus"`.

## Document extractors

- **Run an extractor** [docs]:
  - `POST /api/v1/agents/{agentId}/json/{extractorId}/ask-file` with multipart `file`.
  - The response body is the extracted data, shaped by your schema.
  - The `X-AskFile-Execution-Id` and `X-AskFile-Audit-Id` headers identify the run.
- **Queued vs inline** [docs]. If the extractor has a webhook, the call is queued. Add `?useWebhook=false` to get
  the data in the response; Atelier always does.
- **Other modes** [docs]:
  - Several documents in one call: `…/ask-files`.
  - Extra form fields are passed to the extractor as context.
  - `csv` or `text` can replace `json` in the path.
  - Reading documents uses credits.
- **Optional query parameters** [app]: `ocrEngine`, `pageDefinitions`, `useWebhook`.
- **Polling** [app]: `GET …/json/{extractorId}/executions/{executionId}` returns `{status, output (string), error, fileUrls, …}`.
- **Creating an extractor** [app]:
  - `POST /api/v1/agents/{agentId}/json {title, structure (string), userPrompt, canUseOCR, maxCorrections, checkScript, webhookId, …}`.
  - The extractor hangs off an agent; agents have an `isExtractor` flag.
- **Confidence.** No per-field confidence is documented. Atelier reports how many of the required fields were found,
  and uses per-field confidence when a payload carries it.

## AI Tools [docs]

- **Endpoints:**
  - `GET /api/v1/ai-tools` lists the catalog. Atelier also uses it as the auth probe.
  - `POST /api/v1/ai-tools/{tool}/run {text, secondaryText?, options}` returns `{tool, output, creditsConsumed, truncated}`.
  - `…/run-media` and `…/run-file` for media and files.
- **Tools:** `doc-structure`, `tables`, `translate`, `anonymize`, `summarize`, `minutes`, `email` (mode write|reply,
  tone formal|friendly|commercial|assertive), `rewrite`, `simplify`, `sentiment`, `compare`.
- **Atelier:** set `EVOLUS_RFQ_AI_TOOL=true` to polish the RFQs with `email`.

## Workflows

- **Execute** [docs]:
  - `POST /api/v1/workflows/{id}/execute` with multipart fields: `input`, `file`, `parameters` (a flat JSON
    object), and `callbackUrl` / `callbackMethod` / `callbackApiKey` / `callbackApiKeyName`.
  - Returns 202 `{jobId, executionId, enqueuedAt, traceId}` and the header `X-Workflow-Execution-Id`.
  - A switched-off workflow returns 409.
- **Poll** [docs]: `GET …/executions/{executionId}`. `status` is Pending, Running, Completed or Failed. The full
  record is `{output, error, stepOutputs, consumption, …}` [app].
- **Webhooks and auth.**
  - Webhook deliveries carry `X-Workflow-Execution-Id` and `X-Workflow-Audit-Id` [docs].
  - Outbound webhooks (`POST /api/v1/webhooks {name, url, contentType, apiKeyName, apiKeyValue}`) authenticate with
    **a static header you choose, not a signature** [app].
  - That is why Atelier's quote webhook checks a shared-secret header. It also accepts an HMAC signature for other
    callers.
- **Email triggers** [app].
  - There is no Evolus-provided inbound address: the workflow polls a mailbox you configure.
  - The trigger is "When an email arrives".
  - Mailbox settings: IMAP host, port, username, password and SSL, or Microsoft Graph OAuth; plus folder and
    polling interval.
  - `POST /api/v1/workflows/{id}/test-email-connection` tests the mailbox.
  - Workflows can also start on a schedule (cron, minimum 30 s) [docs].
- **Step types** (UI labels) [app]:
  - Read the document (OCR), Ask an agent, Call a data extractor, Process with AI, Create a file, Send an email,
    Call an endpoint (API), Send on WhatsApp, Automation output, Merge results, Choice, Routing, Repeat for each item,
    Start another automation, AI Tool, Anonymize data, Restore data, Run a script, Decision.
  - Send-email fields: `emailRecipients`, `emailSubjectTemplate`, `emailBodyTemplate`, `emailReplyToSender`,
    `emailAttachResultFile`.
  - Step types are numeric. `GET /api/v1/workflows/step-catalog` lists them.
- **API creation** [app]: `POST /api/v1/workflows`, then `POST /api/v1/workflows/{id}/steps`.

## MCP

- **The Evolus MCP server** [docs].
  - URL: `https://api.evolus.ai/mcp`, streamable HTTP.
  - It gives coding agents tools for "agents, workflows, extractors, libraries and more".
  - The key needs MCP access; granular keys work on both REST and MCP.
  - Config from the docs:

  ```json
  {"mcpServers":{"evolus":{"type":"http","url":"https://api.evolus.ai/mcp",
    "headers":{"X-ApiKey":"<application API key>","X-Application-Id":"<space id>"}}}}
  ```

  - **Adding it to Claude Code** [inferred: standard CLI syntax; Evolus doesn't document it]:

  ```bash
  claude mcp add --transport http evolus https://api.evolus.ai/mcp \
    --header "X-ApiKey: $EVOLUS_API_KEY" --header "X-Application-Id: $EVOLUS_WORKSPACE_ID"
  ```

  - The tool list is not published (UNKNOWN). Run `/mcp` in Claude Code, or a `tools/list` call, once a key exists.
  - Evolus Studio, a desktop app and CLI built on OpenCode, has these tools built in [docs].
- **MCP connectors inside agents.** These connect external MCP servers to an agent and are configured in the
  workspace [event]. A manual connector takes a URL (HTTP or SSE) plus optional headers [app].

## Provisioning through the API [app] [3p]

`backend/scripts/provision_evolus.py` uses these endpoints:

| Resource | Endpoint |
|---|---|
| Agent | `POST /api/v1/agents {name, prompt, language, modelKey, isChatVisible, isExtractor, description}` returns `agentId` |
| Library | `POST /api/v1/memories/simple`, then upload documents, then `POST /api/v1/agents/{id}/memories {memoryId}` |
| Extractor | `POST /api/v1/agents/{agentId}/json {title, structure, userPrompt, canUseOCR}` |
| Webhook | `POST /api/v1/webhooks {name, url, contentType, apiKeyName, apiKeyValue}` |
| Workflow | `POST /api/v1/workflows`, then `…/steps` (numeric `stepType`). We set workflows up in the UI. |

Whether an application key may call every one of these is not documented. Use the UI for anything that fails.

## Hackathon rules relevant to us [event]

- The main agent must use an open model served on AMD (our own vLLM endpoint).
- Use at least two building blocks.
- Drive Evolus from the app through its APIs.
- Judges review "the connected model endpoint, the building blocks used and the API calls" in the event workspace.
- Join with `https://app.evolus.ai/join/AMDACT3`.
- The workspace is free until 15 Nov 2026 (lablab says 31 Oct).

## Still to verify with a key

1. The `/v1/chat/completions` response: are there `usage` and citations?
2. Can an application key call `/memories*`, or is a user key needed?
3. The exact extractor output when `structure` is JSON Schema vs. a field list. Our mapper is lenient.
4. The payload of a "Call an endpoint (API)" step and of webhook deliveries. Our webhook accepts any JSON shape and
   searches it.
5. The MCP `tools/list` contents.
6. The response bodies of the creation endpoints (`agentId` vs `id`). The provisioning script accepts either.

## Verified against the event workspace (2026-10-15)

- `GET /api/v1/ai-tools` with `X-ApiKey` + `X-Application-Id` authenticates (verified live).
- `POST /api/v1/agents` in an event space returns **422 "This space runs only on your own models: connect your model in "Your models" and choose it"**. Every agent, including the extractor's agent, needs the AMD vLLM model connected first. Order of setup: AMD vLLM up → "Your models" in Evolus → then `provision_evolus.py`.
- Workflow step catalog (numeric step types, from the live workspace): Read the document (OCR)=0, Ask an agent=1, Call an endpoint (API)=2, Send an email=3, Merge results=4, Create a file=5, Send on WhatsApp=6, Process with AI=7, Choice (if… else)=8, Repeat for each item=9, Task for the digital employee=10, Start another automation=11, Routing=12, Call a data extractor=13, Automation output=14, Call a number=15, AI Tool=16, Anonymize data=17, Restore data=18, Run a script=19, Decision=20.

## Verified against the event workspace (2026-10-16)

- **Execution parameters are strings.** A JSON number gets HTTP 400 "The execution parameter 'production_quantity'
  must be a string". Atelier stringifies every value (`_flatten`).
- **Parameter limits.** A parameter holds at most 500 characters ("The execution parameter 'rfq_emails' exceeds
  500 characters"), a workflow declares at most 20 parameters, and an undeclared parameter is rejected ("Unknown
  execution parameter 'garment_name': this workflow does not declare it"). So Atelier sends only the declared
  email fields (`rfq_emails`, `rfq_ref`, `kind`; `evolus.EMAIL_WORKFLOW_PARAMS`), splits a long value into
  `rfq_emails`, `rfq_emails__2`, … plus `rfq_emails__parts` (`evolus._chunks`), and the workflow script joins
  them. Everything else (tech pack, PO numbers, …) is in the `input` text.
- **Send an email** sends from the Evolus mailbox, through Microsoft Graph on Evolus's side; no mailbox needs to be
  connected. `emailRecipients` is **literal**: `{{step:<id>.toEmail}}`, `{{output}}` and `{{param:to_email}}` each
  fail at run time with "Call to 'microsoft-graph' failed in SendCoreAsync". Subject and body templates resolve
  `{{step:<id>.path}}`. The step output reads "Email sent to N recipient(s): …".
- A ForEach body can hold a guided Switch whose case keys are email addresses, with an Email step on each branch.
  That is how the Atelier workflows route each drafted email (see `scripts/provision_evolus_workflows.py`).
- Execution record: `{id, workflowId, input, parameters, stepOutputs{"<order>": text}, stepStates, status, error,
  output}`. A Script step that throws fails the run with "The Script step '<name>' failed: <message>".
- **Agent on `own/gemma-4-31b-it` (AMD Token Factory):** latency varies with the upstream, not with Evolus.
  - Short JSON answers, 9 of 11 calls: 1.5–3.6 s. Outliers: 13.7 s and 31 s.
  - A tech-pack-sized answer (about 1,700 characters): 9.6 s and 12.2 s.
  - Upstream errors happen: the agent intermittently returns 422 "Your model … could not answer: The model endpoint
    returned an error", and REST `/agents/{id}/ask` hit it too.
  - `/v1/chat/completions` returns no `usage`. No reasoning text leaks into the content (Gemma 4's thinking is off by
    default).
  - `update_agent` accepts `modelParameters` without a schema for an own model. Setting
    `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 3000}` was followed by 422s, so it was cleared
    again (`{}`).

