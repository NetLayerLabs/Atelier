"""LLM orchestrator: TechPack generation + supplier RFQ drafting.

The agent's brain (services/brain.py) writes both: the Evolus agent whose model is our AMD vLLM endpoint, else
AMD vLLM directly, grounded in the knowledge library and citing it. The JSON is schema-validated with one retry.
v5: there is no template tech pack and no template RFQ - without a working brain these steps fail honestly
(brain.BrainUnavailable) and the pipeline shows a retry.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..models import Design, SupplierEmail, TechPack, TrendAnalysis
from . import brain, direction, money, supplier_view, workspace

log = logging.getLogger("atelier.llm")


# --------------------------------------------------------------------------- live


def _amount(v: Any) -> float:
    """'€1,234.50' / 'USD 98.40' / 98.4 -> 1234.5 / 98.4 (the model sometimes adds a symbol or a code)."""
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v).replace(",", "")) or "x")
    except ValueError:
        return 0.0


def _validate_techpack(quantity: int, currency: str | None = None):
    def v(data: Any) -> TechPack:
        if not isinstance(data, dict):
            raise ValueError("expected object")
        if "techPack" in data and isinstance(data["techPack"], dict):
            data = data["techPack"]
        bom = data.get("billOfMaterials") or data.get("bill_of_materials") or []
        norm_bom = []
        for b in bom:
            if not isinstance(b, dict):
                continue
            cost = _amount(b.get("targetCostPerUnit", b.get("target_cost_per_unit", 0)))
            norm_bom.append({"material": str(b.get("material", "")).strip(),
                             "quantity": str(b.get("quantity", "")).strip(),
                             "targetCostPerUnit": round(cost, 2)})
        meas = data.get("measurements") or {}
        if isinstance(meas, list):
            meas = {str(m.get("name", i)): str(m.get("value", "")) for i, m in enumerate(meas) if isinstance(m, dict)}
        price = _amount(data.get("targetRetailPrice", data.get("target_retail_price", 0)))
        notes = data.get("constructionNotes") or data.get("construction_notes") or []
        if isinstance(notes, str):
            notes = [notes]
        notes = [str(n).strip() for n in notes if str(n).strip()][:12] if isinstance(notes, list) else []
        tp = TechPack.model_validate({
            "garmentName": data.get("garmentName") or data.get("garment_name"),
            "description": data.get("description") or "",
            "billOfMaterials": norm_bom,
            "measurements": {str(k): str(v) for k, v in meas.items()},
            "targetSupplierRegion": data.get("targetSupplierRegion") or data.get("target_supplier_region") or "",
            "targetRetailPrice": price,
            "productionQuantity": quantity,
            "constructionNotes": notes or None,
            "currency": currency,
        })
        if len(tp.bill_of_materials) < 2 or len(tp.measurements) < 3 or not tp.garment_name:
            raise ValueError("tech pack incomplete")
        if tp.target_retail_price <= 0:  # no invented price: a missing retail price is a schema failure (retry)
            raise ValueError("targetRetailPrice missing")
        return tp
    return v


async def live_techpack(trend: TrendAnalysis, design: Design, quantity: int) -> "brain.Thought[TechPack]":
    """Raises brain.BrainUnavailable when no live path worked (the pipeline step shows the error + retry)."""
    trend = direction.effective_trend(trend, design)
    # The directed palette / fabrics, not the trend's originals, so the colour story matches the render.
    eff = direction.effective_trend(trend, design)
    brief = {
        "trend": eff.model_dump(by_alias=True, exclude={"id", "source_image_urls", "created_at"}),
        "design": {"garmentType": design.garment_type, "prompt": design.prompt, "vibe": design.vibe,
                   "imageUrl": design.image_url},
        "productionQuantity": quantity,
    }
    creative = direction.techpack_brief(design)
    if creative:  # v2: the CD's direction must reach the factory
        brief["creativeDirection"] = creative
    sys_msg = (workspace.brand_prompt("senior apparel technical designer") + " Produce factory-ready tech packs that "
               "follow the house brand book (fit blocks, fabric standards, sustainability rules, price architecture). "
               "Respond with ONLY a JSON object - no prose, no markdown fences.")
    ccy = money.brand_currency()  # every price on the tech pack is in the brand's own currency
    unit = ccy or "the brand currency"
    schema = ('{"garmentName": str, "description": str, "billOfMaterials": [{"material": str, "quantity": str, '
              f'"targetCostPerUnit": number ({unit} per finished garment)}}], '
              '"measurements": {"<point of measure>": "<value with unit>"}, '
              f'"targetSupplierRegion": str, "targetRetailPrice": number ({unit}), '
              '"constructionNotes": [str] (3-6 factory construction notes: seams, finishes, closures), '
              '"sources": [numbers of the knowledge passages you followed]}')

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nYour previous reply was not valid JSON for this schema. Return the JSON object only."
        return [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": (
                f"Write a tech pack for this approved design. The garment MUST be a {design.garment_type}. "
                f"Use the trend fabrics and palette. Include 6-9 BOM lines (shell, lining/trims, hardware, thread, labels, CMT) "
                f"and 7-10 measurements for sample size M."
                f"{' Apply every creativeDirection.techPackHints item to the measurements, BOM and description.' if creative else ''}"
                f" Start from the matching brand-book fit block, name the certificate of each shell fabric, and price "
                f"retail inside the brand's multiple. Every price is a plain number in {unit} (no symbol)."
                f"\n\nBrief:\n{json.dumps(brief, indent=2)}\n\n{context}\n\nSchema:\n{schema}{extra}")},
        ]

    query = (f"{design.garment_type} fit block measurements sample size; fabric standards "
             f"{' '.join(eff.key_fabrics[:3])}; sustainability certificates; price architecture "
             f"{design.garment_type}; approved colour standards")
    thought = await brain.think_json("techpack", messages, _validate_techpack(quantity, ccy), knowledge_query=query,
                                     max_tokens=1800)
    thought.value.citations = thought.citations or None
    thought.value.generated_by = thought.route
    return thought


async def live_supplier_emails(tp: TechPack, suppliers: list[dict], design: Design, trend: TrendAnalysis,
                               rfq_ref: str = "") -> "brain.Thought[list[SupplierEmail]]":
    from ..data.suppliers import inbox_for, language_of
    from . import i18n

    sup = [{"supplierName": x["name"], "region": x["region"], "specialty": x["specialty"],
            "certifications": x.get("certifications", []), "language": i18n.name_of(language_of(x))}
           for x in suppliers]

    def validate(data: Any) -> list[SupplierEmail]:
        if isinstance(data, dict):
            data = data.get("emails") or data.get("supplierEmails") or [data]
        if not isinstance(data, list):
            raise ValueError("expected list")
        by_name = {x["name"].lower(): x for x in suppliers}
        out = []
        for i, e in enumerate(data):
            if not isinstance(e, dict):
                continue
            target = by_name.get(str(e.get("supplierName", "")).lower()) or suppliers[min(i, len(suppliers) - 1)]
            subject, body = str(e.get("subject", "")).strip(), str(e.get("body", "")).strip()
            if not subject or not body:
                continue
            lang = language_of(target)
            subject_en = str(e.get("subjectEnglish") or e.get("subject_english") or "").strip()
            body_en = str(e.get("bodyEnglish") or e.get("body_english") or "").strip()
            if lang != "en":
                # v4: the mill's language, with the English version alongside - both are required.
                if not body_en:
                    raise ValueError(f"no English version for {target['name']}")
                if i18n.detect_language(body, default=lang) not in (lang,):
                    raise ValueError(f"RFQ to {target['name']} is not in {i18n.name_of(lang)}")
            # Recipients ALWAYS come from the supplier directory (data/suppliers.inbox_for), never from model output.
            if rfq_ref and rfq_ref not in subject:
                subject = f"{subject} [{rfq_ref}]"
            if subject_en and rfq_ref and rfq_ref not in subject_en:
                subject_en = f"{subject_en} [{rfq_ref}]"
            out.append(SupplierEmail(supplier_name=target["name"], region=target["region"],
                                     to_email=inbox_for(target), subject=subject, body=body, status="drafted",
                                     rfq_ref=rfq_ref or None, language=lang, language_name=i18n.name_of(lang),
                                     kind="rfq",
                                     subject_english=(subject_en or subject) if lang != "en" else None,
                                     body_english=body_en if lang != "en" else None))
        if len(out) < len(suppliers):
            raise ValueError("not enough emails")
        return out[: len(suppliers)]

    # Mills see the supplier-safe view only: no target costs, no retail price, no margin (services/supplier_view.py).
    tp_brief = supplier_view.techpack(tp)
    ccy = tp.currency or money.brand_currency()
    link = supplier_view.public_link(design.image_url)  # only a public https URL works for a mill
    link_rule = (f"Include the design link {link}." if link else
                 "Do not include any link or URL. The specification is in this email; say the design render and a "
                 "spec sheet are available on request by reply.")

    def messages(attempt: int, context: str) -> list[dict]:
        extra = "" if attempt == 0 else "\nReturn ONLY the JSON object."
        return [
            {"role": "system", "content": workspace.persona("sourcing manager") + " Write concise, professional "
                                          "RFQ emails in the house tone of voice. Output JSON only."},
            {"role": "user", "content": (
                f"Draft one RFQ email per supplier for this tech pack. Ask for unit price (full-package FOB, quoted in "
                f"{ccy or 'the brand currency'}), MOQ per colour, lab-dip turnaround, sampling and bulk lead time, "
                f"payment terms and quote validity, and ask the mill to reply with a PDF quote that shows a quote "
                f"number. State the specification (materials, measurements, quantity, required lead time) from the "
                f"tech pack; never mention a target cost, retail price or margin. Put the RFQ reference "
                f"{rfq_ref or '(none)'} in every subject line. Sign as 'Atelier Sourcing Agent'. {link_rule} "
                f"Write each email in the supplier's own language (the \"language\" field; "
                f"formal business register, e.g. 'Gentile team di …' in Italian, 'Caros colegas da …' in European "
                f"Portuguese) and give a faithful English version of it alongside.\n\n"
                f"Tech pack:\n{json.dumps(tp_brief)}\n\nSuppliers:\n{json.dumps(sup, ensure_ascii=False)}\n\n"
                f"{context}\n\n"
                f'Return {{"emails": [{{"supplierName": str, "language": str, "subject": str, "body": str, '
                f'"subjectEnglish": str, "bodyEnglish": str}}], "sources": [passage numbers used]}}{extra}')},
        ]

    query = "RFQ tone of voice quote requirements payment terms " + " ".join(x["name"] for x in suppliers)
    return await brain.think_json("rfq_emails", messages, validate, knowledge_query=query, max_tokens=2200)
