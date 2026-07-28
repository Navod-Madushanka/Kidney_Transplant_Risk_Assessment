# app/schemas/antibody_profile.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AntibodyProfileEntry(BaseModel):
    antigen: str
    mfi: Decimal

    model_config = ConfigDict(from_attributes=True)
