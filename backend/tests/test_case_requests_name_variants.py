import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyotp")


def test_name_variants_preserves_simple_two_token_name():
    from app import person_lookup_matching as matching

    variants = matching._name_variants("Alice Smith")

    assert variants == [("Alice", "Smith")]


def test_name_variants_handles_space_hyphen_and_compound_surnames():
    from app import person_lookup_matching as matching

    variants = matching._name_variants("Ivette Becerra Ortiz")

    assert variants[0] == ("Ivette", "Becerra Ortiz")
    assert ("Ivette", "Becerra-Ortiz") in variants
    assert ("Ivette", "BecerraOrtiz") in variants
    assert ("Ivette", "Ortiz") in variants


def test_name_variants_handles_compound_last_name_without_space_in_source():
    from app import person_lookup_matching as matching

    variants = matching._name_variants("Giovanna Sotelo Solari")

    assert variants[0] == ("Giovanna", "Sotelo Solari")
    assert ("Giovanna", "SoteloSolari") in variants
    assert ("Giovanna", "Sotelo-Solari") in variants


def test_name_variants_includes_middle_last_pair_for_three_token_names():
    from app import person_lookup_matching as matching

    variants = matching._name_variants("John Paul Jones")

    assert ("Paul", "Jones") in variants


def test_three_name_variants_include_full_first_middle_last():
    from app import person_lookup_matching as matching

    variants = matching._three_name_variants("John Paul Jones")

    assert ("John", "Paul", "Jones") in variants


def test_disabled_person_lookup_does_not_dispatch_provider(monkeypatch):
    from app import case_request_lookup_refresh as refresh

    monkeypatch.setattr(refresh, "person_lookup_enabled", lambda: False)

    matches, error = refresh.lookup_matches_for_query("user@example.edu")

    assert matches == []
    assert error == "Person lookup is not enabled."

def test_build_lookup_display_name_includes_middle_name():
    from app import person_lookup_matching as matching

    assert matching._build_lookup_display_name({
        "first_name": "John",
        "middle_name": "Paul",
        "last_name": "Jones",
    }) == "John Paul Jones"


def test_rank_lookup_matches_keeps_typo_tolerant_surname_match():
    from app import person_lookup_matching as matching

    matches = [
        {"first_name": "Mary", "middle_name": "Jane", "last_name": "Neri"},
        {"first_name": "Mary", "middle_name": "Jane", "last_name": "Aikman"},
        {"first_name": "Maura", "middle_name": "Jean", "last_name": "Doherty"},
    ]

    ranked = matching._rank_lookup_matches("Mary Jane Nerri", matches)

    assert [matching._build_lookup_display_name(match) for match in ranked] == ["Mary Jane Neri"]


def test_rank_lookup_matches_keeps_two_token_middle_initial_variants():
    from app import person_lookup_matching as matching

    matches = [
        {"first_name": "Nelson", "last_name": "Lee", "email": "nelson.lee@example.edu", "department_name": "F_IT ARS Infrastructure", "employee_end_date": "2023-06-30"},
        {"first_name": "Nelson", "middle_name": "K", "last_name": "Lee", "email": "nelson.lee2@example.edu", "department_name": "F_IT Security and Policy", "employee_end_date": None},
    ]

    ranked = matching._rank_lookup_matches("Nelson Lee", matches)

    assert [matching._build_lookup_display_name(match) for match in ranked] == ["Nelson Lee", "Nelson K Lee"]


def test_rank_lookup_matches_prefers_richer_exact_first_last_records():
    from app import person_lookup_matching as matching

    matches = [
        {"first_name": "Brian", "last_name": "Smith"},
        {"first_name": "Brian", "middle_name": "E", "last_name": "Smith", "email": "Brian.Smith@example.edu", "department_name": "E_AVC Rsch Admin", "job_title_official": "ADMIN MGR 4", "employee_end_date": None},
        {"first_name": "Brian", "last_name": "Smith"},
    ]

    ranked = matching._rank_lookup_matches("Brian Smith", matches)

    assert [matching._build_lookup_display_name(match) for match in ranked] == ["Brian E Smith", "Brian Smith", "Brian Smith"]


def test_rank_lookup_matches_keeps_compound_first_name_for_two_token_query():
    from app import person_lookup_matching as matching

    matches = [
        {"first_name": "Joan", "last_name": "Neri"},
        {"first_name": "Mary Jane", "last_name": "Neri", "email": "Jane.Neri@example.edu", "department_name": "OPERATING ROOM ML", "employee_end_date": None},
    ]

    ranked = matching._rank_lookup_matches('Jane Neri', matches)

    assert [matching._build_lookup_display_name(match) for match in ranked] == ['Mary Jane Neri']
