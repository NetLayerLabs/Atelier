"""A clearly synthetic TEST brand workspace - test data only, never shipped as app data.

Every name starts with "TEST", every address is on the reserved .test domain (undeliverable), and the numbers are
arbitrary values chosen to exercise the code paths (they describe no real brand or supplier).
"""

from __future__ import annotations

from app.models import Guardrails, now_iso
from app.services import workspace
from app.workspace_models import BrandDocument, BrandProfileInput, MaterialPrice, SupplierCertification, SupplierInput

# (name, city, country, language, categories, certifications, moq, lead weeks, payment terms)
TEST_SUPPLIERS = [
    ("TEST Indigo Denim", "Testville", "Japan", "en", ["denim", "indigo", "selvedge", "chambray"],
     ["GOTS (organic cotton)", "OEKO-TEX Standard 100", "SMETA 4-pillar audit"], 300, 9, "test terms A"),
    ("TEST Lanificio Lana", "Testville", "Italy", "it", ["wool", "barathea", "tweed", "flannel", "gabardine",
                                                        "boucle", "melton"],
     ["GRS (recycled wool)", "RWS (virgin wool)", "amfori BSCI A"], 250, 8, "test terms B"),
    ("TEST Tessitura Seta", "Testville", "Italy", "it", ["silk", "satin", "charmeuse", "jacquard", "brocade",
                                                        "cupro", "organza"],
     ["OEKO-TEX Standard 100", "SA8000"], 200, 7, "test terms C"),
    ("TEST Malhas Malha", "Testville", "Portugal", "pt", ["cashmere", "merino", "alpaca", "mohair", "knit", "yarn"],
     ["GCS (Good Cashmere Standard)", "RWS (merino)"], 300, 7, "test terms D"),
    ("TEST Ripstop Technical", "Testville", "China", "en", ["nylon", "ripstop", "polyester", "technical", "membrane",
                                                           "neoprene", "recycled"],
     ["GRS", "bluesign approved"], 800, 6, "test terms E"),
    ("TEST Conceria Pelle", "Testville", "Italy", "it", ["leather", "suede", "nappa", "shearling"],
     ["LWG Gold"], 150, 10, "test terms F"),
    ("TEST Organic Cotton", "Testville", "India", "en", ["cotton", "canvas", "hemp", "linen", "twill", "poplin",
                                                        "jersey"],
     ["GOTS", "OCS", "SA8000"], 600, 10, "test terms G"),
    # Makers (category "CMT"): the Asian one first, so a non-European round picks it (shortlist rule).
    ("TEST Garment Asia", "Testville", "China", "en", ["CMT"], ["amfori BSCI A", "WRAP Gold"], 500, 5,
     "test terms H"),
    ("TEST Confezioni Europa", "Testville", "Italy", "it", ["CMT"], ["SMETA 4-pillar audit", "ISO 9001"], 150, 7,
     "test terms I"),
]

# (material, category, unit, price) - arbitrary TEST prices, USD, valid from a fixed date.
TEST_PRICES = [
    ("Grade-A Mongolian cashmere", "TEST knit yarns", "m", 72.0),
    ("Recycled cashmere blend", "TEST knit yarns", "m", 38.0),
    ("Extra-fine merino", "TEST knit yarns", "m", 24.0),
    ("14oz selvedge denim", "TEST denim", "m", 17.5),
    ("Organic cotton denim", "TEST denim", "m", 11.0),
    ("Recycled cotton denim", "TEST denim", "m", 8.5),
]
TEST_PRICE_DATE = "2026-01-01"

TEST_BRAND_BOOK = """# TEST Brand - Brand Book

## Fit blocks

TEST rule: jacket fit block, chest and shoulder measured on sample size M.

## Fabric standards

TEST rule: shell fabrics name their certificate.

## Price architecture

TEST rule: retail is a multiple of landed cost.

## RFQ tone of voice

TEST rule: short, polite RFQs that quote the reference.
"""


def email_of(name: str) -> str:
    return f"{workspace._slug(name)}@supplier.test"


def tag_of(name: str) -> str:
    return workspace._slug(name)


def seed(*, guardrails: bool = True, confirm: bool = True) -> None:
    workspace.wipe()
    workspace.save_profile(BrandProfileInput(name="TEST Brand", currency="USD", target_markets=["TEST market"],
                                             voice="TEST voice notes.", default_size_range=["S", "M", "L"],
                                             delivery_promise_weeks=12, preorder_window_days=14))
    for name, city, country, lang, cats, certs, moq, lead, terms in TEST_SUPPLIERS:
        workspace.add_supplier(SupplierInput(
            name=name, city=city, country=country, language=lang, emails=[email_of(name)], categories=cats,
            capabilities=[], certifications=[SupplierCertification(name=c) for c in certs], moq=moq,
            lead_time_weeks=lead, payment_terms=terms))
    workspace.replace_prices([MaterialPrice(material=m, category=c, unit=u, price=p, currency="USD",
                                            supplier="", valid_from=TEST_PRICE_DATE) for m, c, u, p in TEST_PRICES],
                             workspace.provenance("csv", "test-prices.csv", rows=len(TEST_PRICES)))
    doc = BrandDocument(id=workspace.new_document_id(), kind="brand_book", filename="test-brand-book.md",
                        content_type="text/markdown", size=len(TEST_BRAND_BOOK), uploaded_at=now_iso(),
                        chars=len(TEST_BRAND_BOOK))
    workspace.save_document(doc, TEST_BRAND_BOOK.encode(), TEST_BRAND_BOOK)
    if confirm:
        workspace.confirm_suppliers("test")
    if guardrails:
        workspace.save_guardrails(Guardrails(min_gross_margin_pct=65, cost_headroom_pct=75, max_lead_time_weeks=10),
                                  by="test")
