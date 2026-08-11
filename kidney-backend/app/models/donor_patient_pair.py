# app/models/donor_patient_pair.py
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DonorPatientPair(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A patient and donor registered together, so the two lab documents
    that actually cover both of them (HLA typing report, crossmatch report
    -- see PairReportFile) have a real owner instead of being filed under
    one side arbitrarily. See app/services/pair_service.py.

    Authoritative-field split with Donor.intended_recipient_id (which this
    table does NOT replace -- see that column's own docstring): the
    matching engine (exchange_graph_service.load_exchange_pool) reads
    intended_recipient_id, never this table. This table is authoritative
    for document ownership and the stored crossmatch transcription only.
    Registering a pair sets both in the same transaction; pair_service's
    assert_intended_recipient_consistent detects the two drifting apart
    (possible since PUT /donors/{id} can still repoint intended_recipient_id
    without going through this table) rather than silently trusting either.
    """

    __tablename__ = "donor_patient_pairs"
    __table_args__ = (
        # One active pair per (patient, donor) -- soft-deleting frees the
        # combination for re-registration, same pattern as
        # ix_donors_nic_number_active_unique.
        Index(
            "ix_donor_patient_pairs_patient_id_donor_id_active_unique",
            "patient_id",
            "donor_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    donor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("donors.id"), nullable=False, index=True
    )

    # Transcribed verbatim from the crossmatch report. Deliberately no
    # crossmatch_is_positive column -- that's the doctor's own reading,
    # re-entered fresh on every compatibility check's Review step, never
    # OCR-filled and never stored here. See wizardReducer.js's crossmatch
    # block comment for the full contract.
    crossmatch_t_cell_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    crossmatch_b_cell_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    crossmatch_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    crossmatch_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    crossmatch_test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Same OCR-confirmation contract as Patient.hla_typing_verified /
    # Donor.details_verified -- see hla_typing_service._resolve_verified.
    crossmatch_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
