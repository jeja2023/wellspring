"""接警信息字段契约；当前仅用于开发验证。"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseInformationFields(BaseModel):
    """接警编号必填，其他字段为空时保留为空；日期规则待业务确认。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    number: str = Field(alias="接警编号", min_length=1, max_length=80)
    alarm_type: str | None = Field(default=None, alias="接警类型", max_length=10000)
    receiving_unit: str | None = Field(default=None, alias="接警单位", max_length=10000)
    receiving_branch: str | None = Field(default=None, alias="接警分局", max_length=10000)
    alarm_content: str | None = Field(default=None, alias="报警内容", max_length=10000)
    alarm_address: str | None = Field(default=None, alias="报警地址", max_length=10000)
    caller: str | None = Field(default=None, alias="报警人", max_length=10000)
    alarm_time: str | None = Field(default=None, alias="报警时间", max_length=10000)
    caller_phone: str | None = Field(default=None, alias="报警电话", max_length=10000)
    additional_result: str | None = Field(default=None, alias="处警补充结果", max_length=10000)
    feedback_time: str | None = Field(default=None, alias="处警反馈时间", max_length=10000)
    modification_time: str | None = Field(default=None, alias="处警修改时间", max_length=10000)
    standardized_address: str | None = Field(default=None, alias="发生地址（标准地址）", max_length=10000)
    brief_result: str | None = Field(default=None, alias="简要警情及处理结果", max_length=10000)
    category: str | None = Field(default=None, alias="类别", max_length=10000)
    result: str | None = Field(default=None, alias="结果", max_length=10000)
    involved_items: str | None = Field(default=None, alias="涉案物品", max_length=10000)
    apprehended_people: str | None = Field(default=None, alias="抓获人员", max_length=10000)
    tags: str | None = Field(default=None, alias="标签", max_length=10000)
    note: str | None = Field(default=None, alias="备注", max_length=10000)

    @field_validator("number", mode="before")
    @classmethod
    def trim_number(cls, value):
        return value.strip() if isinstance(value, str) else value
