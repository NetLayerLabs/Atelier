"""v5: honest errors. There is no mock fallback: when a service is not configured or fails, the request fails with
a ServiceError, which main.py turns into a 503 `{detail, service, hint, status}` the dashboard shows with a retry."""

from __future__ import annotations

from typing import Optional

HINTS: dict[str, str] = {
    "vision": "Set AMD_VISION_ENDPOINT (and AMD_VISION_MODEL) to an OpenAI-compatible vision model served by vLLM "
              "- docs/AMD_SETUP.md.",
    "diffusion": "Set AMD_DIFFUSION_ENDPOINT to the diffusion server (deploy/diffusion_server.py) - docs/AMD_SETUP.md.",
    "brain": "Set EVOLUS_AGENT_MODEL (+ EVOLUS_API_KEY, EVOLUS_WORKSPACE_ID) for the Evolus agent, or "
             "AMD_VLLM_ENDPOINT for AMD vLLM directly - docs/EVOLUS_SETUP.md, docs/AMD_SETUP.md.",
    "llm": "Set AMD_VLLM_ENDPOINT (and AMD_VLLM_MODEL) - docs/AMD_SETUP.md.",
    "evolus_outreach": "Set EVOLUS_API_KEY, EVOLUS_WORKSPACE_ID and EVOLUS_OUTREACH_WORKFLOW_ID - docs/EVOLUS_SETUP.md.",
    "evolus_negotiation": "Set EVOLUS_API_KEY, EVOLUS_WORKSPACE_ID and EVOLUS_NEGOTIATION_WORKFLOW_ID (or the "
                          "outreach workflow) - docs/EVOLUS_SETUP.md.",
    "evolus_po": "Set EVOLUS_API_KEY, EVOLUS_WORKSPACE_ID and EVOLUS_PO_WORKFLOW_ID (or the outreach workflow) - "
                 "docs/EVOLUS_SETUP.md.",
    "shopify": "Set SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_TOKEN (or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET) - "
               "docs/SHOPIFY_SETUP.md.",
}


class ServiceError(RuntimeError):
    """A real service failed (or is missing). `not_configured` = its env vars are not set."""

    def __init__(self, service: str, message: str, *, hint: Optional[str] = None, not_configured: bool = False):
        super().__init__(message)
        self.service = service
        self.message = message
        self.not_configured = not_configured
        # A setup hint ("set AMD_VISION_ENDPOINT…") only when the service is NOT configured; a configured service
        # that fails (timeout, upstream error) must not tell the presenter to set variables that are already set.
        self.hint = hint if hint is not None else (HINTS.get(service) if not_configured else None)

    @property
    def status(self) -> str:
        return "not_configured" if self.not_configured else "unreachable"


class NotConfigured(ServiceError):
    def __init__(self, service: str, message: str, *, hint: Optional[str] = None):
        super().__init__(service, message, hint=hint, not_configured=True)
