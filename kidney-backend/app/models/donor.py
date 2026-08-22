# app/models/donor.py
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import BloodType, DonorStatus, Race, RhFactor, Sex, SmokingStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Donor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donors"
    # Plain unique=True would keep a soft-deleted donor's NIC permanently
    # reserved (see is_deleted below), blocking re-registration of a real
    # person after their old record was deleted. Scoping the uniqueness to
    # active rows only lets a NIC be reused once its prior record is gone.
    __table_args__ = (
        Index(
            "ix_donors_nic_number_active_unique",
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
    status: Mapped[DonorStatus] = mapped_column(
        Enum(
            DonorStatus,
            name="donor_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=DonorStatus.AVAILABLE,
        server_default=DonorStatus.AVAILABLE.value,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Clinical suitability fields (added 2026-08-08) -- previously the Donor
    # model had nothing beyond demographics + blood type, so a doctor had no
    # way to record or review a candidate donor's medical fitness. All
    # nullable/editable (unlike blood_type/rh_factor, none of this is
    # permanent-once-set). Still purely informational for the *compatibility*
    # pipeline: nothing in match_pipeline.py reads these, and none of these
    # values have an agreed accept/reject threshold from the doctors for that
    # pipeline. They ARE read by services/donor_risk_service.py (added
    # 2026-08-09, see the field group below) for the separate donor
    # safety-assessment screen. Booleans are nullable tri-state (unknown/no/
    # yes) rather than defaulting an unassessed donor to a confirmed "no".
    egfr: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    systolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    has_diabetes: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Donor safety risk-assessment fields (added 2026-08-09) -- inputs to
    # services/donor_risk_service.py's implementation of the Grams et al.
    # (NEJM 2016) living-kidney-donor kidney-failure risk projection; see that
    # module's docstring for the model itself and its citation. All
    # nullable/editable, same rationale as the clinical fields above.
    # `is_smoker` (bool) is replaced by `smoking_status`: the model scores
    # former and current smokers with different coefficients, which a
    # yes/no flag can't represent. `creatinine` and
    # `family_history_kidney_disease` are informational only -- the raw lab
    # value and a standard living-donor screening question -- and are NOT
    # inputs to the projection itself (donor_risk_service.py never reads
    # them for the calculation, only surfaces them alongside it); every
    # other field here is fed directly into the model.
    sex: Mapped[Sex | None] = mapped_column(
        Enum(
            Sex,
            name="sex_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=True,
    )
    race: Mapped[Race | None] = mapped_column(
        Enum(
            Race,
            name="race_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=True,
    )
    smoking_status: Mapped[SmokingStatus | None] = mapped_column(
        Enum(
            SmokingStatus,
            name="smoking_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=True,
    )
    creatinine: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    urine_acr: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    is_on_antihypertensive_medication: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    family_history_kidney_disease: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # OCR verification gate (added 2026-08-08) -- see the matching comment
    # on app/models/patient.py. Donors only need the HLA typing half (no
    # antibody/bead-specificity profile is collected per-donor).
    hla_typing_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # OCR verification gate for person-details fields (added 2026-08-09 —
    # see the matching comment on app/models/patient.py's details_verified).
    details_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Intended recipient (added 2026-08-09) -- most living donors in this
    # system aren't free-floating organs; they're someone's relative,
    # donating only if that specific patient gets a kidney. Before this
    # field, an "available" donor looked identical to a deceased/altruistic
    # donor and was pooled into every other hospital's cross-hospital
    # search regardless of who they actually came in for (see
    # donor_search_service.py's is_deleted/status filter, which this
    # nullable-FK filter joins). NULL means altruistic/deceased -- genuinely
    # poolable. Deliberately no ondelete behavior beyond FK default
    # (RESTRICT): a patient with a donor pointing at them can't be
    # hard-deleted, matching how patients/donors are soft-deleted
    # everywhere else in this codebase.
    #
    # Authoritative for the matching engine (added 2026-08-11) --
    # exchange_graph_service.load_exchange_pool reads this column directly
    # and DonorPatientPair does NOT replace it. A DonorPatientPair row is
    # authoritative for document ownership and the stored crossmatch only;
    # see that model's docstring for the split and how the two are kept
    # from silently drifting apart.
    intended_recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True, index=True
    )

    # LKDPI inputs (added 2026-08-10) -- see app/reference_data/lkdpi_model.py
    # (Massie et al., AJT 2016). `weight_kg` is genuinely new even though
    # `bmi` already exists -- BMI alone can't give the donor/recipient
    # weight ratio the model needs. `is_biologically_related` is a nullable
    # tri-state (null = unknown, not "unrelated") for the same reason every
    # other clinical field on this model is nullable: an unset field must
    # never look like a confirmed "no".
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_biologically_related: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
