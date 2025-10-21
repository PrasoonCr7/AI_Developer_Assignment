import os
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import SQLModel, Session, create_engine, select
from typing import List, Dict, Any
from .models import Document
from .schemas import IngestResponse, ExtractResponse, AskResponse, AuditFinding
from .utils_pdf import extract_pages_from_pdf, heuristic_extract
from .retrieval import SimpleRetriever, extract_answer_span
import shutil
import json
import asyncio

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "..", "samples")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = os.path.join(APP_DIR, "db.sqlite")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SQLModel.metadata.create_all(engine)

app = FastAPI(title="Contract Intelligence API")

# in-memory index
_docs_pages_cache: Dict[int, List[str]] = {}
retriever = SimpleRetriever()

# simple counters for metrics
_metrics = {"ingest_count": 0, "extract_count": 0, "ask_count": 0, "audit_count": 0}

@app.on_event("startup")
def startup_index_existing():
    # load documents from DB into memory index
    with Session(engine) as session:
        docs = session.exec(select(Document)).all()
        pages_map = {}
        for d in docs:
            pages = json.loads(d.metadata.get("pages_json", "[]"))
            pages_map[d.id] = pages
            _docs_pages_cache[d.id] = pages
        if pages_map:
            retriever.index_documents(pages_map)

@app.post("/ingest", response_model=IngestResponse)
async def ingest(files: List[UploadFile] = File(...)):
    """
    Accept 1..n PDFs, extract per-page text, store in DB and update index.
    """
    saved_ids = []
    global _metrics
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files allowed")
        # save to samples folder
        dest = os.path.join(DATA_DIR, f.filename)
        with open(dest, "wb") as out:
            content = await f.read()
            out.write(content)
        # extract pages
        pages = extract_pages_from_pdf(dest)
        # store in DB
        joined = "\n<<PAGE_BREAK>>\n".join(pages)
        from sqlmodel import Session
        doc = Document(filename=f.filename, full_text=joined, metadata={"pages_json": json.dumps(pages)})
        with Session(engine) as session:
            session.add(doc)
            session.commit()
            session.refresh(doc)
            saved_ids.append(doc.id)
            # update in-memory
            _docs_pages_cache[doc.id] = pages
    # reindex all docs (simple approach)
    retriever.index_documents(_docs_pages_cache)
    _metrics["ingest_count"] += len(saved_ids)
    return IngestResponse(document_ids=saved_ids)

@app.post("/extract", response_model=ExtractResponse)
def extract_fields(document_id: int):
    """
    Return structured fields using heuristics.
    """
    global _metrics
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")
        pages = json.loads(doc.metadata.get("pages_json", "[]"))
    heur = heuristic_extract(pages)
    # map heuristics to schema
    resp = ExtractResponse(
        parties=heur.get("parties", []),
        effective_date=heur.get("effective_date"),
        term=heur.get("term"),
        governing_law=heur.get("governing_law"),
        payment_terms=heur.get("payment_terms"),
        termination=heur.get("termination"),
        auto_renewal=heur.get("auto_renewal"),
        confidentiality=heur.get("confidentiality"),
        indemnity=heur.get("indemnity"),
        liability_cap=heur.get("liability_cap"),
        signatories=[{"raw": s} for s in heur.get("signatories_raw", [])]
    )
    _metrics["extract_count"] += 1
    return resp

@app.post("/ask", response_model=AskResponse)
def ask(question: Dict[str,str]):
    """
    RAG-like QA: returns answer + citations (document_id, page, char ranges).
    Input: {"question": "What is the termination notice period?"}
    """
    global _metrics
    q = question.get("question") or question.get("q") or ""
    if not q:
        raise HTTPException(400, "Provide a 'question' field")
    results = retriever.retrieve(q, topk=5)
    if not results:
        return AskResponse(answer="No relevant content found in uploaded documents.", citations=[])
    # pick best sentence and craft short answer
    best = results[0]
    ans_text, sstart, send = extract_answer_span(best["sentence"], q)
    # compute citation char offsets relative to page - we stored sentence start in retrieval as start
    citation = {
        "document_id": best["doc_id"],
        "page": best["page"],
        "start_char": best["start"] + sstart,
        "end_char": best["start"] + send,
        "text": ans_text
    }
    _metrics["ask_count"] += 1
    return AskResponse(answer=ans_text, citations=[citation])

@app.get("/ask/stream")
async def ask_stream(q: str):
    """
    SSE streaming of an answer. Streams the chosen sentence word-by-word as tokens.
    """
    results = retriever.retrieve(q, topk=3)
    if not results:
        async def empty_gen():
            yield "data: No relevant content found.\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")
    best = results[0]
    ans_text, sstart, send = extract_answer_span(best["sentence"], q)
    words = ans_text.split()
    async def event_stream():
        for w in words:
            await asyncio.sleep(0.05)  # pacing
            yield f"data: {w}\n\n"
        # send citation at end
        citation = {"document_id": best["doc_id"], "page": best["page"]}
        yield f"data: {json.dumps({'citation': citation})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/audit", response_model=List[AuditFinding])
def audit(document_id: int):
    """
    Run basic rule checks and return list of findings with severity + evidence spans.
    """
    global _metrics
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")
        pages = json.loads(doc.metadata.get("pages_json", "[]"))
    findings = []
    # check auto-renewal with notice window <30 days (very simple heuristics)
    joined = "\n".join(pages)
    if "auto-renew" in joined.lower() or "auto renew" in joined.lower() or "renew automatically" in joined.lower():
        # look for notice period number
        import re
        m = re.search(r"notice.*?(\d{1,3})\s*(day|days)", joined, re.I)
        if m:
            days = int(m.group(1))
            if days < 30:
                findings.append(AuditFinding(issue="Auto-renewal with short notice", severity="HIGH",
                                             evidence={"snippet": joined[m.start()-80:m.end()+80]}))
            else:
                findings.append(AuditFinding(issue="Auto-renewal found", severity="MEDIUM",
                                             evidence={"snippet": joined[m.start()-80:m.end()+80]}))
        else:
            findings.append(AuditFinding(issue="Auto-renewal clause found (notice period not specified)", severity="MEDIUM",
                                         evidence={"snippet": "auto-renew clause detected"}))
    # unlimited liability
    if "unlimited liability" in joined.lower() or "no limit" in joined.lower():
        findings.append(AuditFinding(issue="Potential unlimited liability", severity="HIGH",
                                     evidence={"snippet": "unlimited liability phrase found"}))
    # broad indemnity
    if "indemnif" in joined.lower() or "hold harmless" in joined.lower():
        findings.append(AuditFinding(issue="Indemnity / Hold harmless clause present", severity="MEDIUM",
                                     evidence={"snippet": "indemnity phrase detected"}))
    _metrics["audit_count"] += 1
    return findings

# admin endpoints
@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return _metrics

# simple webhook emitter - optional: on background tasks you would POST to a URL
@app.post("/webhook/events")
async def receive_webhook(payload: Dict[str,Any]):
    # placeholder to accept registrations if you want; for assignment we just accept event posts.
    return {"status":"received", "payload_size": len(json.dumps(payload))}

# OpenAPI docs available at /docs by default