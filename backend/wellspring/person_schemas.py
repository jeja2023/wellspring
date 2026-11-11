from datetime import date,datetime,timedelta,timezone
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

    @field_validator('birth_date','occurred_on','expected_end_on','due_on',mode='before',check_fields=False)
    @classmethod
    def calendar_date(cls,value):
        if value is None or isinstance(value,date):return value
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('日期须为 YYYY-MM-DD')
        return value


class PersonFields(Input):
    name:str=Field(min_length=1,max_length=120)
    source:str=Field(min_length=1,max_length=200)
    document_type:Literal['NATIONAL_ID','PASSPORT','OTHER']|None=None
    document_number:str|None=Field(default=None,max_length=100)
    birth_date:date|None=None
    phone:str=Field(default='',max_length=100)
    address:str=Field(default='',max_length=1000)
    responsible_user_id:str|None=Field(default=None,max_length=36)

    @model_validator(mode='after')
    def document_pair(self):
        if self.birth_date and self.birth_date>datetime.now(timezone(timedelta(hours=8))).date():raise ValueError('出生日期不能晚于今天')
        if bool(self.document_type)!=bool(self.document_number):raise ValueError('证件类型与号码须同时填写')
        if self.document_number:
            self.document_number=self.document_number.upper().replace(' ','')
            if not re.fullmatch(r'[A-Z0-9.-]{1,100}',self.document_number):raise ValueError('证件号码格式无效')
            if self.document_type=='NATIONAL_ID' and not re.fullmatch(r'[0-9]{17}[0-9X]',self.document_number):raise ValueError('身份证号码应为 18 位')
        return self


class PersonEdit(PersonFields):
    version:int=Field(ge=1)


class Review(Input):
    version:int=Field(ge=1)
    action:Literal['CONFIRM','RETURN','REVOKE']
    note:str=Field(min_length=1,max_length=2000)
    document_no:str=Field(min_length=1,max_length=200)


class RecordInput(Input):
    person_version:int=Field(ge=1)
    kind:Literal['USE','CASE','MEASURE','TEST','FOLLOWUP']
    record_type:str=Field(min_length=1,max_length=40)
    occurred_on:date
    source:str=Field(min_length=1,max_length=200)
    document_no:str=Field(min_length=1,max_length=200)
    basis:str=Field(min_length=1,max_length=2000)
    details:dict[str,str]=Field(default_factory=dict)
    case_id:str|None=Field(default=None,max_length=36)
    replaces_id:str|None=Field(default=None,max_length=36)
    expected_end_on:date|None=None

    @model_validator(mode='after')
    def structured(self):
        types={'USE':{'REPORTED','DETECTED','CONFIRMED','ADDICTION'},'CASE':{'SUSPECT','DEFENDANT','CONVICTED','OTHER'},'MEASURE':{'VOLUNTARY','COMMUNITY','ISOLATED','REHABILITATION'},'TEST':{'SCREENING','LAB','RETEST'},'FOLLOWUP':{'VISIT','SUPPORT'}}
        if self.record_type not in types[self.kind]:raise ValueError('业务类型无效')
        allowed={'USE':{'substance','finding','note'},'CASE':{'case_nature','stage','allegation','outcome','judgment_doc','judgment_effective_on'},'MEASURE':{'decision_org','execution_agency','execution_location','report_due_on','note'},'TEST':{'method','laboratory','result','next_due_on','note'},'FOLLOWUP':{'content','next_due_on','note'}}[self.kind]
        if set(self.details)-allowed or any(len(value)>3000 for value in self.details.values()):raise ValueError('业务详情字段或长度无效')
        for key,value in self.details.items():
            if key.endswith('_on') and value:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('日期格式应为 YYYY-MM-DD')
                date.fromisoformat(value)
        if self.kind=='CASE':
            if not self.case_id or self.details.get('case_nature') not in {'CRIMINAL','ADMINISTRATIVE','OTHER'} or self.details.get('stage') not in {'PROCESSING','INVESTIGATION','PROSECUTION','TRIAL','FINALIZED','CLOSED'}:raise ValueError('请关联案件并填写案件性质和办理阶段')
            if self.details.get('case_nature')!='CRIMINAL' and (self.record_type!='OTHER' or self.details.get('stage') not in {'PROCESSING','CLOSED'}):raise ValueError('刑事诉讼角色和阶段仅用于刑事案件')
            if not self.details.get('allegation'):raise ValueError('请填写涉嫌事项或在案角色依据')
            if self.record_type=='CONVICTED' and (not self.details.get('judgment_doc') or not self.details.get('judgment_effective_on') or self.details.get('stage')!='FINALIZED'):raise ValueError('裁判结论须有生效裁判文书和生效日期')
            if self.details.get('judgment_effective_on') and date.fromisoformat(self.details['judgment_effective_on'])>datetime.now(timezone(timedelta(hours=8))).date():raise ValueError('裁判生效日期不能晚于今天')
        elif self.case_id:raise ValueError('当前业务不接受案件字段')
        if self.kind=='MEASURE' and (not self.details.get('decision_org') or not self.details.get('execution_agency')):raise ValueError('请填写决定机关和实际执行机构')
        if self.expected_end_on and (self.kind!='MEASURE' or self.expected_end_on<self.occurred_on):raise ValueError('预计结束日期不得早于决定日期，且仅用于措施记录')
        if self.kind=='USE' and not self.details.get('finding'):raise ValueError('请填写本次事实或认定内容')
        if self.kind=='TEST' and (self.details.get('result') not in {'POSITIVE','NEGATIVE','INCONCLUSIVE'} or not self.details.get('method') or not self.details.get('laboratory')):raise ValueError('请填写检测机构、方法和结果')
        if self.kind=='FOLLOWUP' and not self.details.get('content'):raise ValueError('请填写随访帮扶内容')
        return self


class Execution(Input):
    version:int=Field(ge=1)
    action:Literal['REPORT','ADMIT','RELEASE','CHANGE','CANCEL']
    occurred_on:date
    note:str=Field(min_length=1,max_length=2000)
    document_no:str=Field(min_length=1,max_length=200)


class RecordEdit(RecordInput):
    version:int=Field(ge=1)


class TaskInput(Input):
    person_version:int=Field(ge=1)
    task_type:Literal['FOLLOWUP','TEST','END_CHECK','REPORT_CHECK']
    title:str=Field(min_length=1,max_length=200)
    due_on:date
    record_id:str|None=Field(default=None,max_length=36)


class TaskComplete(Input):
    version:int=Field(ge=1)
    action:Literal['DONE','CANCELLED']
    note:str=Field(min_length=1,max_length=2000)


class TransferInput(Input):
    person_version:int=Field(ge=1)
    target_org_id:str=Field(min_length=1,max_length=36)
    reason:str=Field(min_length=1,max_length=2000)


class TransferAction(Input):
    version:int=Field(ge=1)
    action:Literal['ACCEPT','REJECT','CANCEL']
    note:str=Field(min_length=1,max_length=2000)
