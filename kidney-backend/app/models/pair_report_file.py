# app/models/pair_report_file.py
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ReportFileCategory
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PairReportFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mirrors PatientReportFile/DonorReportFile exactly, owner is a
    DonorPatientPair -- see that model's docstring for why the two joint
    lab documents (HLA typing, crossmatch) live here instead of on either
    person individually."""

    __tablename__ = "pair_report_files"
    __table_args__ = (
        UniqueConstraint("pair_id", "category", name="uq_pair_report_files_pair_id_category"),
    )

    pair_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donor_patient_pairs.id"), nullable=False, index=True
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
