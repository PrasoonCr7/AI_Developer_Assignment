import fitz  # pymupdf
from typing import List, Tuple, Dict
import re

def extract_pages_from_pdf(path: str) -> List[str]:
    """Return list of page texts (one string per page)."""
    doc = fitz.open(path)
    pages = []
    for p in doc:
        text = p.get_text("text")
        pages.append(text)
    return pages

# Heuristic extraction helpers:

_date_re = re.compile(r"\b(?:Effective Date|Effective as of|Effective)\s*[:\-]?\s*(\w+\s+\d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", re.I)
_gov_law_re = re.compile(r"\b(governed by|governing law|laws of)\s+(the )?([A-Z][A-Za-z ,&.]+)", re.I)
_auto_renewal_re = re.compile(r"\b(auto-?renew(al)?|renew automatically|automatically renews?|renewal term)\b", re.I)
_indemnity_re = re.compile(r"\bindemnif(y|ies|ication)|hold harmless\b", re.I)
_liability_unlimited_re = re.compile(r"\bunlimited liability\b", re.I)
_liability_cap_re = re.compile(r"\blimit(ed)? (liability )?(to )?\s*(USD|\$|EUR|INR|Rs\.?)?[\s]*([0-9\.,]+)", re.I)
_confidentiality_re = re.compile(r"\b(confidential|confidentiality|non-?disclos)\b", re.I)

def heuristic_extract(pages: List[str]) -> Dict[str, any]:
    joined = "\n".join(pages[:8])  # check first few pages for core metadata
    out = {}
    m = _date_re.search(joined)
    if m:
        out["effective_date"] = m.group(1)
    gm = _gov_law_re.search(joined)
    if gm:
        out["governing_law"] = gm.group(3).strip()
    # auto-renewal
    if _auto_renewal_re.search(joined):
        out["auto_renewal"] = "mentioned"
    # confidentiality
    if _confidentiality_re.search(joined):
        out["confidentiality"] = "present"
    if _indemnity_re.search(joined):
        out["indemnity"] = "present"
    lup = _liability_cap_re.search(joined)
    if lup:
        currency = lup.group(3) or ""
        amount = lup.group(5)
        try:
            amount_f = float(amount.replace(",",""))
        except:
            amount_f = None
        out["liability_cap"] = {"amount": amount_f, "currency": currency.strip()}
    # Parties heuristic - simple: look for "Between" or "This Agreement is between"
    parties = []
    between_re = re.compile(r"\b(this (agreement|contract) (is )?(made )?between|between)\b", re.I)
    for i,p in enumerate(pages[:3]):
        if between_re.search(p):
            # try to capture lines after
            lines = [l.strip() for l in p.splitlines() if l.strip()]
            if len(lines) >= 3:
                # take next two distinct lines as parties
                parties.extend(lines[1:4])
    out["parties"] = parties
    # simple signatory search near end pages
    signatories = []
    for p in pages[-3:]:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        for i,l in enumerate(lines):
            if re.search(r"signed|signature|sign(?:ed)? by", l, re.I):
                # gather nearby lines
                nearby = lines[i:i+4]
                signatories.extend(nearby)
    out["signatories_raw"] = signatories
    return out