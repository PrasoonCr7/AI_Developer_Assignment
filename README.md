# AI_Developer_Assignment
A FastAPI app providing a Contract Intelligence API. Upload PDFs (/ingest), extract text and store in SQLite, use heuristics to extract fields (/extract), BM25 retriever for RAG-style Q&amp;A (/ask, /ask/stream), and /audit for risk checks. Uses PyMuPDF, SQLModel, and rank_bm25.
