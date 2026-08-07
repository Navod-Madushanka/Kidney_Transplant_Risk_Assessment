# app/models/patient_report_file.py
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ReportFileCategory
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PatientReportFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patient_report_files"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "category", name="uq_patient_report_files_patient_id_category"
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    category: Mapped[ReportFileCategory] = mapped_column(
        Enum(
            ReportFileCategory,
            name="report_file_category_enum",
            create_type=False,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(nullable=False)
    storage_path: Mapped[str] = mapped_column(nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
