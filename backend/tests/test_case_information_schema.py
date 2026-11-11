import pytest
from pydantic import ValidationError
from wellspring.case_information_schema import CaseInformationFields


def test_only_number_required_and_all_fields_round_trip():
    minimal = CaseInformationFields.model_validate({"接警编号": "  0001  "})
    assert minimal.number == "0001"
    assert minimal.model_dump(by_alias=True)["备注"] is None
    values = {field.alias: "虚构内容" for field in CaseInformationFields.model_fields.values()}
    values["接警编号"] = "A-1"
    assert CaseInformationFields.model_validate(values).model_dump(by_alias=True) == values


@pytest.mark.parametrize("value", [None, "", "   "])
def test_number_is_required(value):
    with pytest.raises(ValidationError):
        CaseInformationFields.model_validate({"接警编号": value})


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        CaseInformationFields.model_validate({"接警编号": "A", "摘要": "不再使用"})
