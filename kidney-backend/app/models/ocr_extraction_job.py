# app/models/ocr_extraction_job.py
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import OcrExtractionJobStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OcrExtractionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A document-extraction batch tracked server-side rather than tied to
    one HTTP connection — the doctor can navigate anywhere in the wizard
    (or lose their connection entirely) while
    app/services/ocr_job_service.py's background task keeps running and
    updating `documents` here; the frontend polls GET
    /ocr/extract-batch/jobs/{id} instead of holding a single long-lived
    streaming request open for the 1.5-3 minutes a bead specificity page
    can take.
    """
    __tablename__ = "ocr_extraction_jobs"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id"), nullable=False, index=True
    )
    # Set when a job is started against a patient that already exists,
    # scoping/tagging it for audit purposes only -- see
    # implementation-prompt-part-j.md J0-J3. Previously also authorised
    # run_extraction_job to auto-save extracted bead-specificity rows to
    # antibody_profiles, unattended, once the job finished; that write was
    # deleted (Part J) after review found it had no guard against
    # overwriting a doctor's already-verified profile, and no way to
    # recover what it deleted -- a background task must never be the thing
    # that destroys clinical data a human entered or confirmed. Nothing in
    # the current frontend passes this field; it stays available for a
    # future caller that wants a job attributable to a patient without
    # granting it any write of its own.
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True, index=True
    )
    status: Mapped[OcrExtractionJobStatus] = mapped_column(
        Enum(
            OcrExtractionJobStatus,
            name="ocr_extraction_job_status_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
        default=OcrExtractionJobStatus.RUNNING,
        server_default=OcrExtractionJobStatus.RUNNING.value,
    )
    # One entry per requested document slot (e.g. "bead_specificity_page_1"),
    # updated in place as ocr_batch_service.stream_batch_extraction's
    # ProgressEvents/DocumentChunks arrive — see
    # ocr_job_service.run_extraction_job for the shape written here and
    # app/schemas/ocr.py's OcrJobDocumentStatus for the shape read back out.
    documents: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # Only set if the background task itself blew up unexpectedly — per-
    # document extraction failures are recorded inside `documents` instead
    # and don't fail the whole job (same tolerance stream_batch_extraction
    # already has).
    error: Mapped[str | None] = mapped_column(String, nullable=True)
