# app/tests/unit/test_cpra_service.py
from app.services.cpra_service import (
    calculate_cpra,
    calculate_population_antigen_frequencies,
)


def test_frequency_counts_each_person_once_even_with_duplicate_antigens():
    population = [
        ["A2", "A2", "B7"],  # duplicate A2 within one person shouldn't double-count
        ["A2"],
        ["B7"],
    ]

    frequencies = calculate_population_antigen_frequencies(population)

    assert frequencies["A2"] == 2 / 3
    assert frequencies["B7"] == 2 / 3


def test_cpra_insufficient_data_below_threshold():
    small_population = [["A2"]] * 50  # only 50 people, below the 100 threshold

    result = calculate_cpra(
        sensitized_antigens=["A2"], population_profiles=small_population
    )

    assert result.has_sufficient_data is False
    assert result.cpra_percentage is None
    assert result.sample_size == 50
    assert result.message == "Not enough data yet to calculate cPRA"


def test_cpra_calculates_once_threshold_met():
    # 100 people: 25 carry A2, everyone else carries something unrelated
    population = [["A2"]] * 25 + [["B7"]] * 75

    result = calculate_cpra(sensitized_antigens=["A2"], population_profiles=population)

    assert result.has_sufficient_data is True
    assert result.cpra_percentage == 25.0
    assert result.sample_size == 100
