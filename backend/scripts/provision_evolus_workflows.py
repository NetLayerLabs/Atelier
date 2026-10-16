"""Build (or rebuild in place) Atelier's two email workflows in Evolus, through the Evolus MCP server.

    cd backend
    uv run python scripts/provision_evolus_workflows.py --dry-run          # show recipients and steps
    uv run python scripts/provision_evolus_workflows.py                    # create / update both workflows
    uv run python scripts/provision_evolus_workflows.py --recipient you@example.com --only outreach

Workflows (both switched ON, ids printed for backend/.env):
  outreach  "Atelier - send RFQ emails"     EVOLUS_OUTREACH_WORKFLOW_ID  (RFQs and counter-offers)
  po        "Atelier - send purchase order" EVOLUS_PO_WORKFLOW_ID

Why there is one email step per recipient (verified live 2026-10-16): the "Send an email" step sends from the
Evolus mailbox, and its recipients are LITERAL addresses. {{step:…}}, {{output}} and {{param:…}} are not resolved
in the recipients field (the mailer then fails with "Call to 'microsoft-graph' failed"). Subject and body
templates do resolve placeholders. So each email Atelier drafted is routed by a Switch on its address to the email
step of that address. The recipients are the brand's supplier directory (each supplier's RFQ override address if
set, else its contact email: data/suppliers.inbox_for) plus any --recipient. An address that has no email step is
NOT sent and the run reports it (all unknown -> the run fails; some -> emailStatus "partial", Atelier shows
"queued"). **Re-run this script after adding a supplier or changing an RFQ override.** It replaces the steps of
the workflows named in backend/.env in place, so their ids stay the same.

Graph:  Script "Parse the drafted emails" (params.rfq_emails -> [{toEmail, toKey, subject, bodyHtml, …}])
        -> Repeat for each item { Switch on toKey -> Send an email (one per address) | default: "Not a recipient" }
        -> Script "Summarise what was sent" -> Automation output
Output: {"emailStatus": "sent" | "partial", "sentCount", "failedCount", "notSentCount", "rfqRef", "kind",
         "emails": [{toEmail, supplierName, subject, result, error}]}; Atelier marks the RFQs / PO "sent" on
         emailStatus "sent" (services/evolus.outreach_status).

Needs EVOLUS_USER_API_KEY (personal key) and EVOLUS_WORKSPACE_ID in backend/.env.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402

MCP_URL = "https://api.evolus.ai/mcp"

PARSE = r"""
// Long values arrive in pieces (Evolus caps a parameter at 500 characters): rfq_emails, rfq_emails__2, ...
var raw = params.rfq_emails || '';
var parts = parseInt(params.rfq_emails__parts || '1', 10) || 1;
for (var p = 2; p <= parts; p++) raw += (params['rfq_emails__' + p] || '');
var list;
try { list = typeof raw === 'string' ? JSON.parse(raw) : (raw || []); }
catch (e) { throw new Error('rfq_emails is not valid JSON: ' + e.message); }
if (!Array.isArray(list)) list = [list];
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
var out = [];
for (var i = 0; i < list.length; i++) {
  var e = list[i] || {};
  var to = String(e.toEmail || e.to_email || e.to || '').trim();
  if (!to) continue;
  out.push({
    toEmail: to,
    toKey: to.toLowerCase(),
    subject: String(e.subject || ''),
    bodyHtml: '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5">'
              + esc(e.body).replace(/\r?\n/g, '<br>') + '</div>',
    supplierName: String(e.supplierName || e.supplier_name || ''),
    rfqRef: String(e.rfqRef || params.rfq_ref || ''),
    kind: String(e.kind || params.kind || 'rfq')
  });
}
if (!out.length) throw new Error('rfq_emails holds no email with a toEmail address');
return out;
"""

NOT_RECIPIENT = ("return { notSent: 'no email step for ' + (data && data.toEmail) + ' in this workflow: re-run "
                 "scripts/provision_evolus_workflows.py after changing the supplier directory' };")

SUMMARY = r"""
var emails = (sources[0] && sources[0].data) || [];
var res = (sources[1] && sources[1].data) || [];
var results = [], ok = 0, failed = 0, skipped = 0, reasons = [];
for (var i = 0; i < emails.length; i++) {
  var r = res[i], err = null, result = 'handed to the Evolus mailer';
  if (r && typeof r === 'object' && r.error) { err = String(r.error); result = 'failed'; failed++; }
  else if (r && typeof r === 'object' && r.notSent) { err = String(r.notSent); result = 'not sent'; skipped++; }
  else if (typeof r === 'string' && r.length) { ok++; }
  else { err = 'no result from the email step'; result = 'failed'; failed++; }
  if (err) reasons.push(emails[i].toEmail + ': ' + err);
  results.push({ toEmail: emails[i].toEmail, supplierName: emails[i].supplierName, subject: emails[i].subject,
                 result: result, error: err });
}
if (ok === 0) throw new Error('no email was sent. ' + reasons.join(' | '));
return { emailStatus: (failed + skipped) === 0 ? 'sent' : 'partial', sentCount: ok, failedCount: failed,
         notSentCount: skipped, rfqRef: params.rfq_ref || '', kind: params.kind || 'rfq', emails: results };
"""


def _p(name: str, desc: str, required: bool = False) -> dict[str, Any]:
    return {"name": name, "type": "string", "description": desc, "required": required}


# Evolus limits (verified live 2026-10-16): a parameter holds at most 500 characters, a workflow declares at most 20
# parameters, and undeclared keys are accepted. So we declare only what the workflow script reads (the drafted
# emails, split into pieces by services/evolus._chunks, plus rfq_ref and kind); Atelier's other values (tech pack,
# garment name, PO numbers, ...) are still sent, undeclared, and stay on the execution record.
MAX_DECLARED = 20
RFQ_PIECES = MAX_DECLARED - 3  # rfq_emails__parts, rfq_ref, kind; the rest are rfq_emails pieces (17 x 480 chars)

PARAMS = [
    _p("rfq_emails", "JSON array of drafted emails [{supplierName, toEmail, subject, body, rfqRef, kind, language}], "
                     "piece 1", True),
    *[_p(f"rfq_emails__{i}", f"piece {i} of rfq_emails") for i in range(2, RFQ_PIECES + 1)],
    _p("rfq_emails__parts", "how many pieces rfq_emails was split into (Evolus caps a parameter at 500 chars)"),
    _p("rfq_ref", "Atelier RFQ reference, e.g. ATL-run_ab12cd"),
    _p("kind", "rfq | counter_offer | purchase_order"),
]
assert len(PARAMS) <= MAX_DECLARED
SPECS: dict[str, dict[str, Any]] = {
    "outreach": {
        "env": "EVOLUS_OUTREACH_WORKFLOW_ID", "attr": "evolus_outreach_workflow_id",
        "name": "Atelier - send RFQ emails",
        "description": "Sends each RFQ email Atelier drafted (rfq_emails: to, subject, body in the mill's language) "
                       "from the Evolus mailbox; also counter-offers (kind=counter_offer). Recipients = the brand's "
                       "supplier directory. Output {emailStatus: sent|partial, ...}.",
        "params": PARAMS,
    },
    "po": {
        "env": "EVOLUS_PO_WORKFLOW_ID", "attr": "evolus_po_workflow_id",
        "name": "Atelier - send purchase order",
        "description": "Emails Atelier's purchase order (rfq_emails holds the one PO email to the mill's address) "
                       "from the Evolus mailbox. Output {emailStatus: sent, ...}.",
        "params": PARAMS,
    },
}


class MCP:
    def __init__(self, user_key: str, app_id: str):
        self.h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                  "X-User-ApiKey": user_key, "X-Application-Id": app_id}
        self.n = 1
        r = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "atelier", "version": "1"}}})
        if r.headers.get("mcp-session-id"):
            self.h["Mcp-Session-Id"] = r.headers["mcp-session-id"]
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, body: dict) -> httpx.Response:
        r = httpx.post(MCP_URL, headers=self.h, json=body, timeout=180)
        if r.status_code >= 400:
            raise SystemExit(f"Evolus MCP HTTP {r.status_code}: {r.text[:200]}")
        return r

    def call(self, tool: str, args: dict[str, Any]) -> Any:
        self.n += 1
        r = self._post({"jsonrpc": "2.0", "id": self.n, "method": "tools/call",
                        "params": {"name": tool, "arguments": args}})
        t = r.text
        if "data:" in t:
            t = [ln[5:] for ln in t.splitlines() if ln.startswith("data:")][-1]
        res = json.loads(t)
        out = res.get("result", res)
        text = "\n".join(c.get("text", "") for c in out.get("content") or []) if isinstance(out, dict) else ""
        if "error" in res or (isinstance(out, dict) and out.get("isError")):
            raise SystemExit(f"{tool} failed: {(text or json.dumps(res))[:400]}")
        try:
            return json.loads(text)
        except ValueError:
            return text


def recipients(extra: list[str]) -> list[str]:
    from app.data.suppliers import all_suppliers, inbox_for

    seen: dict[str, None] = {}
    for a in [inbox_for(s) for s in all_suppliers()] + list(extra):
        a = (a or "").strip().lower()
        if a and "@" in a:
            seen.setdefault(a, None)
    return list(seen)


def build_steps(mcp: MCP, wf: str, addrs: list[str]) -> None:
    def add(body: dict[str, Any]) -> str:
        r = mcp.call("add_workflow_step", {"workflowId": wf, "requestJson": json.dumps(body)})
        if not isinstance(r, dict) or not r.get("id"):
            raise SystemExit(f"add_workflow_step returned no id: {str(r)[:200]}")
        return str(r["id"])

    def cfg(d: dict) -> str:
        return json.dumps(d)

    parse = add({"name": "Parse the drafted emails", "stepType": "Script", "stepConfigJson": cfg({
        "script": PARSE, "outputStructure": json.dumps([{"toEmail": "", "toKey": "", "subject": "", "bodyHtml": "",
                                                          "supplierName": "", "rfqRef": "", "kind": ""}])})})
    loop = add({"name": "For each email", "stepType": "ForEach", "inputStepIds": [parse], "stepConfigJson": cfg({
        "mode": "guided", "field": "", "parallel": False, "continueOnItemError": True})})
    cases = [{"key": a, "label": a} for a in addrs]
    sw = add({"name": "Route by recipient", "stepType": "Switch", "loopGroupId": loop, "inputStepIds": [loop],
              "stepConfigJson": cfg({"mode": "guided", "field": "toKey", "cases": cases})})
    for a in addrs:
        add({"name": f"Send to {a}", "stepType": "Email", "loopGroupId": loop, "inputStepIds": [sw],
             "inputBranches": {sw: a}, "emailRecipients": a,
             "emailSubjectTemplate": "{{step:%s.subject}}" % sw, "emailBodyTemplate": "{{step:%s.bodyHtml}}" % sw,
             "emailReplyToSender": False, "emailAttachResultFile": False, "createDoc": False})
    add({"name": "Not a recipient of this workflow", "stepType": "Script", "loopGroupId": loop, "inputStepIds": [sw],
         "inputBranches": {sw: "default"}, "stepConfigJson": cfg({"script": NOT_RECIPIENT})})
    summ = add({"name": "Summarise what was sent", "stepType": "Script", "inputStepIds": [parse, loop],
                "stepConfigJson": cfg({"script": SUMMARY})})
    add({"name": "Automation output", "stepType": "Output", "inputStepIds": [summ]})


def provision(mcp: MCP, which: str, addrs: list[str]) -> str:
    spec = SPECS[which]
    wf = str(getattr(get_settings(), spec["attr"]) or "").strip()
    if wf:
        detail = mcp.call("get_workflow_detail", {"workflowId": wf})
        steps = detail.get("steps") or [] if isinstance(detail, dict) else []
        # steps in a loop body first, then the rest last-to-first, so nothing deleted is still read by another step
        for s in sorted(steps, key=lambda s: (s.get("loopGroupId") is None, -(s.get("order") or 0))):
            mcp.call("delete_workflow_step", {"workflowId": wf, "stepId": s["id"]})
        mcp.call("update_workflow", {"workflowId": wf, "requestJson": json.dumps({
            "name": spec["name"], "description": spec["description"], "tags": ["atelier"],
            "parameters": spec["params"]})})
        print(f"{which}: replacing the steps of the workflow in {spec['env']}")
    else:
        r = mcp.call("create_workflow", {"requestJson": json.dumps({
            "name": spec["name"], "description": spec["description"], "tags": ["atelier"], "isActive": False,
            "enableAuditKpi": False, "auditCompareBaseline": 0, "multiFileMode": 0, "emailProviderType": 1,
            "emailPollingEnabled": False, "emailPollingIntervalSeconds": 300, "emailMarkAsRead": False,
            "imapPort": 993, "imapUseSsl": True, "parameters": spec["params"]})})
        wf = str(r.get("id") if isinstance(r, dict) else "")
        if not wf:
            raise SystemExit(f"create_workflow returned no id: {str(r)[:200]}")
        print(f"{which}: created - put this in backend/.env:  {spec['env']}={wf}")
    build_steps(mcp, wf, addrs)
    mcp.call("update_workflow", {"workflowId": wf, "requestJson": json.dumps({"name": spec["name"], "isActive": True})})
    print(f"{which}: '{spec['name']}' switched on · {len(addrs)} recipient email step(s)")
    return wf


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipient", action="append", default=[], help="an extra address to give an email step")
    ap.add_argument("--only", choices=sorted(SPECS), help="only this workflow")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = get_settings()
    addrs = recipients(a.recipient)
    print(f"recipients ({len(addrs)}): {', '.join(addrs) or '-'}")
    if not addrs:
        print("No recipients: add suppliers (with an email or RFQ override) in the Brand workspace, or pass --recipient.")
        return 2
    if a.dry_run:
        return 0
    if not (s.evolus_user_api_key and s.evolus_workspace_id):
        print("EVOLUS_USER_API_KEY and EVOLUS_WORKSPACE_ID must be set in backend/.env")
        return 2
    mcp = MCP(s.evolus_user_api_key, s.evolus_workspace_id)
    for which in [a.only] if a.only else list(SPECS):
        provision(mcp, which, addrs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
