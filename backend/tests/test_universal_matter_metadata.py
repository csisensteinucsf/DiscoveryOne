import pytest
from pydantic import ValidationError

from app import schemas, system_admin
from app.custodians_summary import DirectoryCustodianInput, _normalize_directory_email


def test_directory_custodian_profile_requires_identity_and_campus():
    profile = DirectoryCustodianInput(
        first_name="Jane",
        last_name="Doe",
        email="Jane.Doe@example.edu",
        campus="Main",
        department="Legal",
        employee_id="E100",
        title="Counsel",
        employment_status="Active",
    )

    assert profile.name == "Jane Doe"
    assert _normalize_directory_email(profile.email) == "jane.doe@example.edu"
    assert profile.department == "Legal"
    assert profile.employee_id == "E100"

    with pytest.raises(ValidationError):
        DirectoryCustodianInput(last_name="Doe", email="jane@example.edu", campus="Main")


def test_matter_types_are_normalized_unique_and_reserve_other():
    values = system_admin._normalize_matter_types([
        " General Litigation ",
        "general litigation",
        "Other",
        "Subpoena Request",
    ])

    assert values == ["General Litigation", "Subpoena Request"]


def test_matter_metadata_is_part_of_case_create_and_update_schemas():
    created = schemas.CaseCreate(
        name="Matter One",
        campus="Main",
        matter_type="Internal Investigation",
    )
    updated = schemas.CaseUpdate(campus="Remote", matter_type="Other custom type")

    assert created.campus == "Main"
    assert created.matter_type == "Internal Investigation"
    assert updated.campus == "Remote"
    assert updated.matter_type == "Other custom type"