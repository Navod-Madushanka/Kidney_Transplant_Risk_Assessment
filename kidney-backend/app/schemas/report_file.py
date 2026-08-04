# app/schemas/report_file.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReportFileCategory


class ReportFileResponse(BaseModel):
    id: uuid.UUID
    category: ReportFileCategory
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
