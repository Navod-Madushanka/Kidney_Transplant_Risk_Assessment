# app/schemas/antibody_profile.py
from decimal import Decimal

from pydantic import BaseModel


class AntibodyProfileEntry(BaseModel):
    antigen: str
    mfi: Decimal