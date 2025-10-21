from typing import Optional
from sqlmodel import SQLModel, Field, JSON
import datetime

class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    uploaded_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    metadata: Optional[dict] = Field(default_factory=dict, sa_column=JSON)
    # full_text is concatenated pages with special markers, but we also store pages separately in metadata
    full_text: str