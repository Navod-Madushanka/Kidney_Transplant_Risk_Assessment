# app/models/patient.py
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BloodType, RhFactor
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patients"
    # Patients are strictly doctor-isolated everywhere else in this codebase
    # (no cross-doctor access at all, unlike donors -- see
    # get_patient_by_id_for_doctor). A bare global-unique nic_number
    # contradicted that: two doctors independently treating a real person
    # who happens to share an NIC with someone else's patient would crash
    # with an unhandled 500 (found 2026-08-03). Scoping uniqueness to
    # (doctor_id, nic_number) matches the isolation model -- a doctor still
    # can't register the same NIC twice, but two different doctors now can.
    # Sharing a specific patient across doctors is a real future need (with
    # the owning doctor's explicit permission), but that's a separate,
    # not-yet-built feature, not this constraint.
    #
    # Scoped to active rows only (postgresql_where) -- otherwise a
    # soft-deleted patient's NIC stays permanently reserved, blocking
    # re-registration of a real person after their old record was deleted
    # (found 2026-08-04, via the compatibility-check wizard's inline patient
    # creation step hitting a false-positive "already registered" conflict).
    __table_args__ = (
        Index(
            "uq_patients_doctor_id_nic_number_active",
            "doctor_id",
            "nic_number",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    date_of_birth: Mapped[date] = mapped_column(nullable=False)
    nic_number: Mapped[str | None] = mapped_column(nullable=True, index=True)
    blood_type: Mapped[BloodType] = mapped_column(
        Enum(
            BloodType,
            name="blood_type_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    rh_factor: Mapped[RhFactor] = mapped_column(
        Enum(
            RhFactor,
            name="rh_factor_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # OCR verification gate (added 2026-08-08): defaults True (trusted) for
    # manually-entered data -- these only ever go False when
    # hla_typing_service.replace_patient_hla_typing / antibody_profile_
    # service.replace_patient_antibody_profiles are called with
    # ocr_verified=False, meaning "this write came from OCR extraction and a
    # doctor has not yet confirmed it against the source document."
    # POST /compatibility/check refuses to even call run_match_pipeline
    # while either is False (see app/api/compatibility.py's precondition
    # check, right alongside its patient/donor-not-found checks), rather
    # than trusting a vision-LLM misread into a hard reject. Kept as two
    # separate flags (not one) since HLA typing and the antibody/bead-
    # specificity profile are re-verified independently, from separate
    # source documents.
    hla_typing_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    antibody_profile_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
