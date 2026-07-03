# app/reference_data/cpra_settings.py
"""
cPRA calculation policy settings.

cPRA is calculated from this system's own patient + donor population data,
not a fixed external reference table. Below this sample size, there isn't
enough data in the system yet to produce a statistically meaningful result.
"""

MINIMUM_POPULATION_SAMPLE_SIZE = 100