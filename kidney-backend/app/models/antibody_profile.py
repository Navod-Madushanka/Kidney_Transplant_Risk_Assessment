# app/models/antibody_profile.py
import uuid

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AntibodyPanel
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AntibodyProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "antibody_profiles"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"), nullable=False, index=True
    )
    antigen: Mapped[str] = mapped_column(nullable=False)
    mfi: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # Part I (bead-row identity / tile reconciliation) -- all three
    # nullable, and deliberately so: a row transcribed by a doctor by hand
    # (or one that predates this column) has no source Bead code/page to
    # report, and that's the honest representation, not an error state.
    #
    # bead_id -- the source chart's own Bead column, zero-padded to 3
    # digits (see ocr-service's bead_reconciliation.coerce_bead_id). Bead
    # IDs repeat across the two panel pages, so this is NOT unique on its
    # own -- see `panel` below.
    bead_id: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # panel -- which of the two bead-specificity pages this row came from.
    # Set by the backend from the upload slot, never inferred from antigen
    # content (a misread "DQ4" as "B44" would silently reclassify the
    # row) -- see ocr_batch_service.py's SLOT_PAGE_PANEL.
    panel: Mapped[AntibodyPanel | None] = mapped_column(
        Enum(
            AntibodyPanel,
            name="antibody_panel_enum",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=True,
    )
    # extraction_conflict -- every candidate MFI reconciliation saw when
    # tiles disagreed on this bead (see ocr-service's
    # bead_reconciliation.ReconciledRow.conflict), preserved as JSONB so a
    # doctor confirming one value doesn't erase the fact that it was
    # contested. Null means either no OCR conflict, or this row has no OCR
    # origin at all (bead_id is also null in that case).
    extraction_conflict: Mapped[list | None] = mapped_column(JSONB, nullable=True)
