from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class IngestResponse(BaseModel):
    document_ids: List[int]

class ExtractResponse(BaseModel):
    parties: List[str] = []
    effective_date: Optional[str] = None
    term: Optional[str] = None
    governing_law: Optional[str] = None
    payment_terms: Optional[str] = None
    termination: Optional[str] = None
    auto_renewal: Optional[str] = None
    confidentiality: Optional[str] = None
    indemnity: Optional[str] = None
    liability_cap: Optional[Dict[str, Any]] = None  # {amount: float, currency: str}
    signatories: List[Dict[str,str]] = []

class AskResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]  # {document_id, page, start, end, text}

class AuditFinding(BaseModel):
    issue: str
    severity: str
    evidence: Dict[str,Any]
    