# app/models/enums.py
import enum


class BloodType(str, enum.Enum):
    O = "O"
    A = "A"
    B = "B"
    AB = "AB"