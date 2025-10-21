## 🚀 Features

### 1. Ingest (`POST /ingest`)
Upload one or more PDF files.  
The API stores metadata and extracts plain text using **PyMuPDF (fitz)**.  
It returns `document_id` for each uploaded contract.

### 2. Extract (POST /extract)

Given a document_id, it extracts and returns structured fields like:

parties[]

effective_date

term

governing_law

payment_terms

termination

auto_renewal

confidentiality

indemnity

liability_cap (number + currency)

signatories[]


### 3. Ask (POST /ask)

Ask a question about the uploaded contract.
The answer is generated using simple keyword search within the stored document text (simulating a RAG approach).


### 4. Audit (POST /audit)

Performs rule-based checks to detect risky clauses, such as:

Auto-renewal with less than 30 days’ notice

Unlimited liability

Broad indemnity clauses


### 5. Stream (GET /ask/stream)

Simulated streaming (SSE/WebSocket-style) for live token output when asking a question.

### 6. Admin Routes

GET /healthz → Health check

GET /metrics → Basic metrics (docs uploaded, questions asked, etc.)

GET /docs → Swagger/OpenAPI UI

## Tech Stack

FastAPI – main web framework

PyMuPDF (fitz) – for PDF text extraction

UUID + in-memory storage – simple local DB substitute

uvicorn – for running the API

Docker – for containerized local deployment


Run the container:

docker run -p 8000:8000 contract-intel-api


## Open your browser:

http://localhost:8000/docs

🧾 Example Public Contracts Used

Here are some public domain contract PDFs you can test with:

Mutual NDA Example (OneNDA)

Master Service Agreement Sample

Terms of Service Template

Put them inside a /sample_contracts folder to test ingestion.

