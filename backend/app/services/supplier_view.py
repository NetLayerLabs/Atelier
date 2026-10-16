"""What a supplier may see of a tech pack, and which links may go into a supplier email.

The tech pack carries the brand's own economics: a target cost per BOM line, the retail price and (through them) the
margin. Mills must never see those - a target cost is the brand's negotiating position. Everything that goes to a
mill (the RFQ prompt, the outreach workflow's parameters) uses `techpack()`: specs, measurements, materials,
quantities and the delivery deadline only.

Links: the design render is served from PUBLIC_BASE_URL. A mill can only open it when that is a public https URL;
`public_link()` returns None for localhost / private / plain-http addresses, so no dead link is ever emailed.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Optional
from urllib.parse import urlparse

from ..models import TechPack

# Never sent to a supplier (brand economics). Kept as a list so a test can assert none of them leak.
PRIVATE_FIELDS = ("targetRetailPrice", "targetCostPerUnit", "citations", "generatedBy", "customerEvidence",
                  "currency")


def techpack(tp: TechPack) -> dict[str, Any]:
    """The supplier-safe view: specification and quantities, no target costs, no retail price, no margin."""
    from . import sizes, sourcing

    out: dict[str, Any] = {
        "garmentName": tp.garment_name,
        "description": tp.description,
        "billOfMaterials": [{"material": b.material, "quantity": b.quantity} for b in tp.bill_of_materials],
        "measurements": dict(tp.measurements),
        "productionQuantity": tp.production_quantity,
        "sizeRange": sizes.size_range(tp),
    }
    if tp.colorway:
        out["colorway"] = list(tp.colorway)
    if tp.construction_notes:
        out["constructionNotes"] = list(tp.construction_notes)
    if tp.target_supplier_region:
        out["sourcingRegion"] = tp.target_supplier_region
    weeks = sourcing.lead_budget_weeks()
    if weeks:
        out["requiredLeadTimeWeeks"] = int(weeks)  # the delivery deadline, as a bulk lead time
    return out


def _public_host(host: str) -> bool:
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." in host  # a DNS name
    return ip.is_global


def public_link(url: Optional[str]) -> Optional[str]:
    """`url` if a supplier could open it (public https), else None."""
    if not url:
        return None
    u = urlparse(url)
    if u.scheme != "https" or not _public_host(u.hostname or ""):
        return None
    return url
