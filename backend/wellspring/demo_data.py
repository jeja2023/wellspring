"""Explicit, additive synthetic development fixtures. Never run during app startup."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import secrets
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from .access_models import Role
from .access_policy import CODES
from .ai_models import AiRun
from .analysis_models import AnalysisAsset, AnalysisAssetEvent
from .analysis_rules import validate_config
from .intake_models import IntakeCaseLink
from .intelligence_models import ClueDelivery, DeliveryEvent
from .models import (Audit, Case, CaseImportBatch, CaseImportRow, CaseInformation,
                     CaseRelation, CaseRelationEvent, Clue, ClueCaseLink,
                     ClueImportBatch, IntelligenceEvent, InvestigationTask,
                     Organization, PersonCaseCandidate, PersonCaseCandidateEvent,
                     PersonDraft, User)
from .person_models import PersonEvent, PersonRecord, PersonTask, PersonTransfer
from .person_schemas import PersonFields, RecordInput
from .place_models import (GeoLocation, GeoLocationEvent, Place, PlaceEvent,
                           PlaceIncident, PlaceInspection)
from .security import password_hash
from .wastewater_models import (WastewaterResult, WastewaterResultEvent,
                               WastewaterSample, WastewaterSite)

LABEL = '【演示】'
SOURCE = '虚构测试数据，仅用于界面和流程演示'
DATASET = 'wellspring-demo-v1'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


class DemoBuilder:
    def __init__(self, db, actor, instant):
        self.db, self.actor, self.org, self.instant = db, actor, actor.org_id, instant
        self.today = instant.astimezone(timezone(timedelta(hours=8))).date()
        self.counts = Counter()
        self.credentials = []

    def identity(self, key):
        return str(uuid5(NAMESPACE_URL, f'{DATASET}/{self.org}/{key}'))

    def at(self, days=0, hours=0):
        return self.instant - timedelta(days=days, hours=hours)

    def add(self, model_type, key, **values):
        identity = self.identity(key)
        previous = self.db.get(model_type, identity)
        if previous is not None:
            raise ValueError('发现不完整的旧演示数据；本次回滚，请核对原导入报告')
        row = model_type(id=identity, **values)
        self.db.add(row)
        self.db.flush()
        self.counts[model_type.__tablename__] += 1
        return row

    def person_event(self, person, key, action, record=None, actor=None, payload=None, days=0):
        return self.add(PersonEvent, key, person_id=person.id, org_id=person.org_id,
                        record_id=record.id if record else None, actor_id=(actor or self.actor).id,
                        action=action, note=LABEL + SOURCE,
                        payload_json=encoded(payload) if payload else None, created_at=self.at(days))

    def location(self, kind, row, index):
        # WGS84 synthetic points around the application's Wuxi initial viewport.
        longitude = round(120.297066 + ((index % 6) - 2.5) * .004, 6)
        latitude = round(31.576634 + ((index // 6) - 1.5) * .003, 6)
        snapshot = dict(resource_type=kind, resource_id=row.id, longitude=longitude,
                        latitude=latitude, source=LABEL + SOURCE, version=1,
                        coordinate_system='WGS84')
        location = self.add(GeoLocation, f'location/{kind}/{index}', org_id=row.org_id,
                            resource_type=kind, resource_id=row.id, longitude=longitude,
                            latitude=latitude, source=LABEL + SOURCE, updated_by=self.actor.id)
        self.add(GeoLocationEvent, f'location-event/{kind}/{index}', location_id=location.id,
                 org_id=row.org_id, actor_id=self.actor.id, snapshot_json=encoded(snapshot))

    def accounts(self):
        business = sorted(code for code in CODES if not code.startswith('system.') and code != 'intake.restore')
        reader = sorted(code for code in business if code.endswith('.read'))
        roles = [self.add(Role, f'role/{kind}', code=f'demo_{kind}_{self.org[:8]}',
                          name=LABEL + name, description=SOURCE, permissions_json=encoded(permissions))
                 for kind, name, permissions in [('business', '业务演练员', business),
                                                  ('reviewer', '独立核验员', business),
                                                  ('reader', '只读观察员', reader)]]
        city = self.add(Organization, 'org/city', name=f'{LABEL}清源测试支队-{self.org[:6]}', unit_type='CITY')
        branch = self.add(Organization, 'org/branch', name=f'{LABEL}清源测试大队-{self.org[:6]}',
                          unit_type='BRANCH', parent_id=city.id)
        station = self.add(Organization, 'org/station', name=f'{LABEL}清源测试派出所-{self.org[:6]}',
                           unit_type='STATION', parent_id=branch.id)
        people = {}
        for key, org, role in [('operator', self.db.get(Organization, self.org), roles[0]),
                               ('reviewer', self.db.get(Organization, self.org), roles[1]),
                               ('observer', self.db.get(Organization, self.org), roles[2]),
                               ('city', city, roles[0]), ('branch', branch, roles[0]),
                               ('station', station, roles[0])]:
            username = f'demo_{key}_{self.org[:6]}'
            if self.db.scalar(select(User.id).where(User.username == username)):
                raise ValueError('演示账号名称已被占用；未修改现有账号')
            password = secrets.token_urlsafe(18)
            row = self.add(User, f'user/{key}', username=username, org_id=org.id,
                           role_id=role.id, is_admin=False, password_hash=password_hash(password))
            people[key] = row
            self.credentials.append(dict(username=username, password=password, organization=org.name))
        self.operator, self.reviewer = people['operator'], people['reviewer']
        self.city, self.branch, self.station, self.people = city, branch, station, people

    def cases_and_intakes(self):
        self.cases = []
        for index in range(24):
            row = self.add(Case, f'case/{index}', org_id=self.org,
                           number=f'DEMO-{self.org[:6]}-AJ-{index+1:03}',
                           title=LABEL + ['线索核查关联案件', '场所巡查关联案件', '接警转办演练'][index % 3] + f'{index+1:02}',
                           status='DRAFT', created_at=self.at(index % 28))
            self.cases.append(row)
        for index in range(28):
            when = self.at(index % 28)
            row = self.add(CaseInformation, f'intake/{index}', org_id=self.org,
                           number=f'DEMO-{self.org[:6]}-JJ-{index+1:03}',
                           alarm_type=['咨询求助', '情况反映', '线索移交', '巡查反馈'][index % 4],
                           receiving_unit=LABEL + '测试受理岗', receiving_branch=LABEL + '测试单位',
                           alarm_content=LABEL + f'第{index+1}号虚构接警，核对来源并登记处理意见。',
                           alarm_address=LABEL + f'清源测试路{index+1}号', caller=LABEL + f'来电人{index+1:02}',
                           caller_phone='未提供（演示）', alarm_time=when.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
                           additional_result=LABEL + '已完成初步登记', feedback_time=when.date().isoformat(),
                           modification_time=when.date().isoformat(), standardized_address=LABEL + '测试辖区',
                           brief_result=LABEL + ['待核查', '已反馈', '已转办'][index % 3],
                           category=['咨询', '线索', '其他'][index % 3], result=LABEL + '按演练流程办理',
                           involved_items='虚构资料，无真实物品', apprehended_people='无（演示）',
                           tags='演示,测试', note=SOURCE, created_by=self.actor.id, created_at=when)
            if index < 8:
                from .case_information_schema import CaseInformationFields
                snapshot = CaseInformationFields(**{name: getattr(row, name) for name in CaseInformationFields.model_fields}).model_dump(by_alias=True)
                self.add(IntakeCaseLink, f'intake-link/{index}', org_id=self.org, intake_id=row.id,
                         case_id=self.cases[index].id, source_version=1, source_number=row.number,
                         source_snapshot=encoded(snapshot), created_case=False, basis=LABEL + SOURCE,
                         created_by=self.actor.id, created_at=when)
        for index in range(8):
            relation = self.add(CaseRelation, f'case-relation/{index}', org_id=self.org,
                                source_case_id=self.cases[index].id, target_case_id=self.cases[index+8].id,
                                relation_type='RELATED_TO' if index % 2 else 'COOPERATE_WITH',
                                basis=LABEL + '虚构来源相互关联，仅供关系界面演示', created_by=self.actor.id)
            self.add(CaseRelationEvent, f'case-relation-event/{index}', org_id=self.org,
                     relation_id=relation.id, actor_id=self.actor.id, action='CREATE',
                     after_status='ACTIVE', note=LABEL + SOURCE)
        for index, status in enumerate(['PREVIEW', 'COMPLETED', 'PARTIAL']):
            batch = self.add(CaseImportBatch, f'case-import/{index}', org_id=self.org, actor_id=self.actor.id,
                             source=LABEL + f'CSV导入样例-{status}', digest=hashlib.sha256(f'demo-csv-{index}'.encode()).hexdigest(),
                             mapping_version='DEV-1', status=status, created_at=self.at(index+1),
                             completed_at=None if status == 'PREVIEW' else self.at(index+1))
            for offset in range(4):
                case = self.cases[16+offset] if status != 'PREVIEW' else None
                error = status == 'PARTIAL' and offset == 3
                self.add(CaseImportRow, f'case-import-row/{index}/{offset}', batch_id=batch.id,
                         line_number=offset+2, number='' if error else (case.number if case else f'DEMO-CSV-{self.org[:6]}-{offset+1}'),
                         title=LABEL + f'导入样例{offset+1}', preview_status='ERROR' if error else 'NEW',
                         result_status=None if status == 'PREVIEW' else 'ERROR' if error else 'CREATED',
                         reason=LABEL + '缺少案件编号' if error else '', case_id=None if error or case is None else case.id)

    def intelligence(self):
        batches = [self.add(ClueImportBatch, f'clue-import/{index}', org_id=self.org, actor_id=self.actor.id,
                            filename=f'演示线索导入-{index+1}.xlsx', content_sha256=hashlib.sha256(f'demo-clues-{index}'.encode()).hexdigest(),
                            total=8, created_at=self.at(index+2)) for index in range(2)]
        self.clues = []
        for index in range(24):
            reviewed = index < 20
            clue = self.add(Clue, f'clue/{index}', org_id=self.org, title=LABEL + f'测试辖区情况核查-{index+1:02}',
                            summary=LABEL + '虚构巡查资料与接警信息待核对。请记录核查依据、办理过程及结果，不对应现实对象。',
                            source=LABEL + ['接警转办', '场所巡查', '资料整理'][index % 3],
                            status='REVIEWED' if reviewed else 'DRAFT', created_by=self.operator.id,
                            reference_no=f'DEMO-{self.org[:6]}-QB-{index+1:03}',
                            priority='IMPORTANT' if index % 5 == 0 else 'NORMAL',
                            import_batch_id=batches[index//8].id if index < 16 else None,
                            suggested_due_date=self.today + timedelta(days=index % 9-3), created_at=self.at(index+1),
                            version=2 if reviewed else 1)
            self.clues.append(clue)
            self.add(IntelligenceEvent, f'clue-created/{index}', org_id=self.org, clue_id=clue.id,
                     actor_id=self.operator.id, action='CREATED', after_status='DRAFT', note=LABEL + SOURCE,
                     created_at=self.at(index+1, 6))
            if reviewed:
                self.add(IntelligenceEvent, f'clue-reviewed/{index}', org_id=self.org, clue_id=clue.id,
                         actor_id=self.reviewer.id, action='REVIEWED', before_status='DRAFT', after_status='REVIEWED',
                         note=LABEL + '虚构资料独立核验演示', created_at=self.at(index+1, 5))
            if index < 16:
                status = ['OPEN', 'RETURNED', 'PENDING_REVIEW', 'CLOSED'][index % 4]
                submitter = self.operator if status in {'PENDING_REVIEW', 'CLOSED', 'RETURNED'} else None
                task = self.add(InvestigationTask, f'investigation/{index}', org_id=self.org, clue_id=clue.id,
                                objective=LABEL + '核对虚构来源、填写反馈并进行独立复核',
                                due_date=self.today + timedelta(days=index % 7-2),
                                assignee_id=self.operator.id if status == 'PENDING_REVIEW' else self.actor.id,
                                status=status, last_submitter_id=submitter.id if submitter else None,
                                result_code='INSUFFICIENT' if status == 'RETURNED' else 'NO_FINDING' if submitter else None,
                                version={'OPEN':1, 'PENDING_REVIEW':2, 'CLOSED':3, 'RETURNED':3}[status], created_at=self.at(index+1))
                steps = [('CREATED', None, 'OPEN', self.actor)]
                if status != 'OPEN': steps.append(('SUBMIT', 'OPEN', 'PENDING_REVIEW', self.operator))
                if status in {'RETURNED', 'CLOSED'}: steps.append(('RETURN' if status == 'RETURNED' else 'CLOSE', 'PENDING_REVIEW', status, self.reviewer))
                for offset, (action, before, after, actor) in enumerate(steps):
                    self.add(IntelligenceEvent, f'task-event/{index}/{offset}', org_id=self.org, clue_id=clue.id,
                             task_id=task.id, actor_id=actor.id, action=action, before_status=before,
                             after_status=after, note=LABEL + '核查工单状态演练', created_at=self.at(index+1, 3-offset))
            if index < 8:
                self.add(ClueCaseLink, f'clue-case/{index}', org_id=self.org, clue_id=clue.id,
                         case_id=self.cases[index].id, basis=LABEL + SOURCE, created_by=self.actor.id)

    def persons(self):
        self.persons_list = []
        for index in range(18):
            verified = index < 12
            profile_days = 29-index//2 if verified else 18-index
            record_days = 20 if verified else max(0, profile_days-1)
            check_days = 15 if verified else max(0, profile_days-2)
            data = dict(name=LABEL + f'测试人员{index+1:02}', source=SOURCE, document_type='OTHER',
                        document_number=f'DEMO-{self.org[:6]}-PERSON-{index+1:03}',
                        birth_date=self.today-timedelta(days=30*365+index*70),
                        phone='未提供（演示）', address=LABEL + f'清源测试小区{index+1}号', responsible_user_id=self.actor.id)
            PersonFields(**data)
            person = self.add(PersonDraft, f'person/{index}', org_id=self.org, **data,
                              verification_status='VERIFIED' if verified else 'UNVERIFIED', created_by=self.operator.id,
                              responsible_org_id=self.org, verified_by=self.reviewer.id if verified else None,
                              verified_at=self.at(22) if verified else None, created_at=self.at(profile_days))
            self.persons_list.append(person)
            self.person_event(person, f'person-created/{index}', 'PROFILE_CREATED', actor=self.operator, days=profile_days)
            if verified: self.person_event(person, f'person-verified/{index}', 'IDENTITY_CONFIRM', actor=self.reviewer, days=22)
            specs = [('USE', 'REPORTED', {'substance':'合成演练指标', 'finding':LABEL + '虚构事实待核实'}),
                     ('CASE', 'OTHER', {'case_nature':'ADMINISTRATIVE', 'stage':'PROCESSING', 'allegation':LABEL + '虚构在案角色依据'}),
                     ('MEASURE', ['COMMUNITY','REHABILITATION','ISOLATED','VOLUNTARY'][index % 4],
                      {'decision_org':LABEL + '测试决定单位', 'execution_agency':LABEL + '测试执行机构',
                       'report_due_on':(self.today-timedelta(days=10)).isoformat(), 'note':SOURCE}),
                     ('TEST', 'LAB', {'method':'演示实验室检测', 'laboratory':LABEL + '测试实验室',
                                      'result':['NEGATIVE','INCONCLUSIVE','POSITIVE'][index % 3],
                                      'next_due_on':(self.today+timedelta(days=index-3)).isoformat()}),
                     ('FOLLOWUP', 'VISIT', {'content':LABEL + '虚构随访与支持记录',
                                          'next_due_on':(self.today+timedelta(days=index % 7)).isoformat()})]
            for kind, record_type, details in specs:
                if not verified and kind in {'CASE','MEASURE'}:continue
                check = 'VERIFIED' if verified and index % 4 != 3 else 'RETURNED' if index % 4 == 3 else 'PENDING'
                end = self.today+timedelta(days=index-3) if kind == 'MEASURE' else None
                payload = dict(person_version=1, kind=kind, record_type=record_type, occurred_on=self.today-timedelta(days=20),
                               source=SOURCE, document_no=f'DEMO-{kind}-{index+1:03}', basis=LABEL + SOURCE,
                               details=details, case_id=self.cases[index].id if kind == 'CASE' else None, expected_end_on=end)
                RecordInput(**payload)
                state = ('ACTIVE' if index % 3 else 'DECIDED') if kind == 'MEASURE' else 'RECORDED'
                record = self.add(PersonRecord, f'person-record/{index}/{kind}', person_id=person.id, org_id=self.org,
                                  manager_org_id=self.org, **{key:value for key,value in payload.items() if key not in {'person_version','details'}},
                                  details_json=encoded(details), verification_status=check, state=state,
                                  actual_start_on=self.today-timedelta(days=15) if kind == 'MEASURE' and state == 'ACTIVE' and check == 'VERIFIED' else None,
                                  created_by=self.operator.id, updated_by=self.operator.id,
                                  verified_by=self.reviewer.id if check == 'VERIFIED' else None,
                                  verified_at=self.at(check_days) if check == 'VERIFIED' else None, created_at=self.at(record_days))
                if kind == 'MEASURE' and check != 'VERIFIED':record.state='DECIDED'
                self.person_event(person, f'person-record-created/{index}/{kind}', 'RECORD_CREATED', record, actor=self.operator, days=record_days)
                if check != 'PENDING':self.person_event(person, f'person-record-check/{index}/{kind}', 'RECORD_CONFIRM' if check == 'VERIFIED' else 'RECORD_RETURN', record, actor=self.reviewer, days=check_days)
                if kind == 'MEASURE' and record.actual_start_on:
                    self.person_event(person, f'person-execute/{index}', 'MEASURE_REPORT' if record_type in {'COMMUNITY','REHABILITATION'} else 'MEASURE_ADMIT', record, days=15)
                if kind in {'MEASURE','TEST','FOLLOWUP'} and check == 'VERIFIED':
                    due = end if kind == 'MEASURE' else self.today+timedelta(days=index-3)
                    done = index % 5 == 4
                    task = self.add(PersonTask, f'person-task/{index}/{kind}', person_id=person.id, record_id=record.id,
                                    org_id=self.org, task_type={'MEASURE':'END_CHECK','TEST':'TEST','FOLLOWUP':'FOLLOWUP'}[kind],
                                    title=LABEL + {'MEASURE':'核对措施期限及解除依据','TEST':'后续检测待办','FOLLOWUP':'后续随访待办'}[kind],
                                    due_on=due, status='DONE' if done else 'OPEN', created_by=self.operator.id,
                                    result_note=LABEL + '演示核对完成' if done else '', completed_by=self.actor.id if done else None,
                                    completed_at=self.at(0) if done else None)
                    self.person_event(person, f'person-task-created/{index}/{kind}', 'TASK_CREATED', record, payload={'id':task.id}, days=14)
            if index < 8:
                candidate = self.add(PersonCaseCandidate, f'candidate/{index}', org_id=self.org, person_id=person.id,
                                     case_id=self.cases[index+12].id, basis=LABEL + '历史候选示例，尚未确认案件关系', created_by=self.actor.id)
                self.add(PersonCaseCandidateEvent, f'candidate-event/{index}', org_id=self.org,
                         candidate_id=candidate.id, actor_id=self.actor.id, action='CREATE', note=LABEL + SOURCE)
        # Two distinct verified subjects with no pending measures can demonstrate handoff.
        for index in [0, 1]:
            person = self.persons_list[index]
            self.add(PersonTransfer, f'person-transfer/{index}', person_id=person.id, source_org_id=self.org,
                     target_org_id=self.branch.id, requested_by=self.actor.id, reason=LABEL + '虚构责任移交演练')
            self.person_event(person, f'person-transfer-event/{index}', 'TRANSFER_REQUEST')

    def places_and_water(self):
        for index in range(12):
            place = self.add(Place, f'place/{index}', org_id=self.org, code=f'DEMO-{self.org[:6]}-CS-{index+1:03}',
                             name=LABEL + ['青禾公寓','星河酒吧','清源文娱中心','梧桐街区','测试服务点'][index % 5] + f'{index+1:02}',
                             kind=['APARTMENT','BAR','ENTERTAINMENT','STREET','OTHER'][index % 5], district=LABEL + ['东片区','西片区','南片区'][index % 3],
                             address=LABEL + f'测试路{index+1}号', responsible=self.operator.username,
                             management_basis=LABEL + SOURCE, review_on=self.today+timedelta(days=index-3),
                             active=index != 11, created_by=self.actor.id, created_at=self.at(index+1))
            self.location('PLACE', place, index)
            self.add(PlaceEvent, f'place-created/{index}', org_id=self.org, place_id=place.id,
                     resource_id=place.id, actor_id=self.actor.id, action='CREATED', note=LABEL + SOURCE,
                     snapshot_json=encoded(dict(id=place.id, name=place.name, kind=place.kind)))
            inspection = self.add(PlaceInspection, f'inspection/{index}', org_id=self.org, place_id=place.id,
                                  inspected_on=self.today-timedelta(days=7), findings=LABEL + '虚构巡查：登记设施维护与资料核对事项',
                                  due_on=self.today+timedelta(days=index-3), status='DONE' if index % 3 == 0 else 'OPEN',
                                  result_note=LABEL + '演示复查完成' if index % 3 == 0 else '',
                                  completed_by=self.reviewer.id if index % 3 == 0 else None,
                                  completed_at=self.at(1) if index % 3 == 0 else None, created_by=self.operator.id)
            self.add(PlaceEvent, f'inspection-event/{index}', org_id=self.org, place_id=place.id,
                     resource_id=inspection.id, actor_id=self.operator.id, action='INSPECTED', note=LABEL + SOURCE,
                     snapshot_json=encoded(dict(id=inspection.id, status=inspection.status, findings=inspection.findings)))
            status = ['DRAFT','OPEN','SUBMITTED','CLOSED','RETURNED'][index % 5]
            incident = self.add(PlaceIncident, f'incident/{index}', org_id=self.org, place_id=place.id,
                                title=LABEL + f'场所情况核对-{index+1:02}', occurred_at=self.at(index+1),
                                source=LABEL + '虚构巡查反馈', facts=LABEL + '虚构现场情况，仅用于核验、反馈、办结流程测试',
                                material_ref=f'DEMO-MATERIAL-{index+1:03}', status=status,
                                disposition=LABEL + '已完成虚构核查，待独立复核' if status in {'SUBMITTED','CLOSED'} else '',
                                last_editor_id=self.operator.id, created_by=self.operator.id,
                                submitted_by=self.operator.id if status in {'SUBMITTED','CLOSED'} else None,
                                clue_id=self.clues[index].id if status in {'OPEN','SUBMITTED','CLOSED'} else None)
            self.location('INCIDENT', incident, index+2)
            self.add(PlaceEvent, f'incident-event/{index}', org_id=self.org, place_id=place.id,
                     resource_id=incident.id, actor_id=self.operator.id, action='INCIDENT_CREATED', note=LABEL + '预置虚构事件状态示例',
                     snapshot_json=encoded(dict(id=incident.id, title=incident.title, status=incident.status)))
        for site_index in range(6):
            site = self.add(WastewaterSite, f'water-site/{site_index}', org_id=self.org,
                            code=f'DEMO-{self.org[:6]}-WS-{site_index+1:02}', name=LABEL + f'清源采样点{site_index+1:02}',
                            district=LABEL + ['东片区','西片区','南片区'][site_index % 3], plant_name=LABEL + '测试水处理厂',
                            catchment=LABEL + '虚构汇水范围，不对应真实人群', active=site_index != 5,
                            state_note=SOURCE, created_by=self.actor.id, created_at=self.at(27-site_index))
            self.location('WASTEWATER', site, site_index+9)
            for offset in range(14):
                sample = self.add(WastewaterSample, f'water-sample/{site_index}/{offset}', org_id=self.org, site_id=site.id,
                                  code=f'DEMO-{self.org[:6]}-S{site_index+1}-{offset+1:02}', sampled_at=self.at(13-offset),
                                  sampling_method='COMPOSITE', collector=self.operator.username, flow_m3_day=Decimal('12000.000000'),
                                  quality='FLAGGED' if offset == 12 and site_index else 'VALID', note=LABEL + SOURCE,
                                  created_by=self.operator.id, created_at=self.at(13-offset))
                for analyte_index, analyte in enumerate(['甲基苯丙胺','氯胺酮']):
                    state = 'REVIEWED' if site_index == 0 or offset < 10 else 'DRAFT' if offset % 2 else 'RETURNED'
                    detection = 'BELOW_LOQ' if offset == 11 else 'NOT_DETECTED' if offset == 10 else 'QUANTIFIED'
                    value = Decimal(30+site_index*8+((offset*7+analyte_index*11) % 29)).quantize(Decimal('.000001'))
                    result = self.add(WastewaterResult, f'water-result/{site_index}/{offset}/{analyte_index}',
                                      org_id=self.org, sample_id=sample.id, analyte=analyte, detection=detection,
                                      concentration=value if detection == 'QUANTIFIED' else None,
                                      quantification_limit=Decimal('1.000000'), laboratory=LABEL + '清源测试实验室',
                                      analysis_method='LC-MS/MS（演示）', report_number=f'DEMO-R-{site_index}-{offset}-{analyte_index}',
                                      note=LABEL + SOURCE, state=state, created_by=self.operator.id,
                                      reviewed_by=self.reviewer.id if state != 'DRAFT' else None,
                                      review_note=LABEL + ('核对完成' if state == 'REVIEWED' else '请补充虚构报告信息') if state != 'DRAFT' else '',
                                      created_at=self.at(13-offset), version=2 if state != 'DRAFT' else 1)
                    snapshot = dict(id=result.id, sample_id=sample.id, analyte=analyte, detection=detection,
                                    concentration=result.concentration, state=state, version=result.version)
                    self.add(WastewaterResultEvent, f'water-result-event/{site_index}/{offset}/{analyte_index}', org_id=self.org,
                             result_id=result.id, actor_id=self.reviewer.id if state != 'DRAFT' else self.operator.id,
                             action='CONFIRM' if state == 'REVIEWED' else 'RETURN' if state == 'RETURNED' else 'CREATE',
                             note=LABEL + '预置检测流程演示', snapshot=encoded(snapshot))

    def analysis(self):
        rows = {}
        for kind in ['PROJECT','MODEL','TACTIC']:
            rows[kind] = []
            for index in range(9):
                categories = {'PROJECT':['DATASET','ENTITY','RELATION'], 'MODEL':['COLLISION','SCORE','FLOW'],
                              'TACTIC':['CLUE','CASE','COMPREHENSIVE']}
                category = categories[kind][index % 3]
                config = {'fields':[{'name':'来源编号','type':'text','required':True}, {'name':'待核验数量','type':'number','required':False}]}
                if kind == 'MODEL':
                    config = {'COLLISION':{'mode':'all','conditions':[{'field':'待核验数量','operator':'gte','value':3}]},
                              'SCORE':{'rules':[{'field':'资料完整','operator':'eq','value':True,'points':50},
                                                {'field':'来源可核对','operator':'eq','value':True,'points':50}]},
                              'FLOW':{'steps':[{'name':'收集资料','description':'使用虚构资料'}, {'name':'独立核验','description':'人工核对并记录依据'}]}}[category]
                if kind == 'TACTIC':config = {'steps':'1. 收集演示资料\n2. 核对来源与关联\n3. 记录待核验事项\n4. 人工复核归档', 'applicability':SOURCE}
                validate_config(kind, category, config)
                state = 'ACTIVE' if index < 6 else 'DRAFT' if index < 8 else 'ARCHIVED'
                row = self.add(AnalysisAsset, f'analysis/{kind}/{index}', org_id=self.org, kind=kind,
                               code=f'DEMO-{self.org[:6]}-{kind}-{index+1:02}',
                               name=LABEL + {'PROJECT':'资料结构项目','MODEL':'业务分析模型','TACTIC':'核查技战法'}[kind] + f'{index+1:02}',
                               category=category, description=LABEL + '仅处理手工虚构样例，不自动运行真实业务数据',
                               config_json=encoded(config), project_id=rows['PROJECT'][index % 6].id if kind != 'PROJECT' else None,
                               model_id=rows['MODEL'][index % 6].id if kind == 'TACTIC' else None,
                               status=state, created_by=self.actor.id, updated_by=self.actor.id,
                               created_at=self.at(index+1), updated_at=self.at(index))
                rows[kind].append(row)
                self.add(AnalysisAssetEvent, f'analysis-event/{kind}/{index}', asset_id=row.id, actor_id=self.actor.id,
                         org_id=self.org, action='CREATED', note=LABEL + '预置虚构资料和状态',
                         snapshot_json=encoded(dict(id=row.id, kind=kind, name=row.name, code=row.code, category=category,
                                                   status=state, version=1, configuration=config)))

    def ai_history(self):
        for index in range(24):
            mode = ['summary','extract','qa','dashboard'][index % 4]
            status = 'FAILED' if index == 21 else 'CANCELLED' if index == 22 else 'SUCCEEDED'
            output = LABEL + '预置研判结果示例（未调用模型）\n\n' + {
                'summary':'资料摘要：测试辖区已登记接警、线索及场所巡查记录。来源和关联均为虚构，仍需人工核验。',
                'extract':'时间：演示周期内\n地点：虚构测试辖区\n对象：演示记录\n待核实：来源、办理依据和关联关系。',
                'qa':'根据虚构资料，建议先核对记录来源，再检查待办及独立复核情况；资料不足时不作业务结论。',
                'dashboard':'统计说明：可查看接警、案件、人员、线索、业务模型及采样记录的数量和变化。全部为预置测试数据，不能用于实际业务判断。'
            }[mode]
            self.add(AiRun, f'ai-run/{index}', org_id=self.org, actor_id=self.actor.id, mode=mode, status=status,
                     model='demo-fixture-no-model-call', service_version=0,
                     input_sha256=hashlib.sha256(f'demo-ai-{index}'.encode()).hexdigest(), input_chars=80,
                     output_text=output if status == 'SUCCEEDED' else '',
                     error_code='DEMO_FAILURE' if status == 'FAILED' else '',
                     error_message=LABEL + '模拟失败状态，未发送模型请求' if status == 'FAILED' else LABEL + '模拟取消状态' if status == 'CANCELLED' else '',
                     duration_ms=1200, created_at=self.at(index)-timedelta(seconds=3), started_at=self.at(index)-timedelta(seconds=2),
                     completed_at=self.at(index), prompt_tokens=None, completion_tokens=None)

    def hierarchical_deliveries(self):
        # Existing organizations keep their type/hierarchy. Valid demo flows use new demo units.
        for index in range(10):
            incoming = index % 2 == 0
            owner = self.people['city'] if incoming else self.people['branch']
            target = self.people['branch'] if incoming else self.people['station']
            clue = self.add(Clue, f'flow-clue/{index}', org_id=owner.org_id,
                            title=LABEL + f'层级流转演练{index+1:02}', summary=LABEL + SOURCE,
                            source=LABEL + '测试支队录入', status='REVIEWED', reference_no=f'DEMO-FLOW-{self.org[:6]}-{index}',
                            created_by=owner.id, priority='NORMAL', created_at=self.at(4))
            status = ['OPEN','PROCESSING','PENDING_REVIEW','RETURNED','CLOSED'][index//2]
            snapshot = {name:getattr(clue,name) for name in ['title','summary','source','reference_no','priority']}
            row = self.add(ClueDelivery, f'flow/{index}', clue_id=clue.id, sender_org_id=owner.org_id,
                           recipient_org_id=target.org_id, sender_id=owner.id,
                           assignee_id=target.id if status != 'OPEN' else None, objective=LABEL + '虚构层级下发与逐级反馈',
                           due_date=self.today+timedelta(days=index-3), allow_station=True, snapshot_json=encoded(snapshot),
                           status=status, disposition_text=LABEL + '虚构核查处理' if status in {'PENDING_REVIEW','CLOSED','RETURNED'} else '',
                           feedback_text=LABEL + '虚构反馈结果' if status in {'PENDING_REVIEW','CLOSED','RETURNED'} else '',
                           result_code='NO_FINDING' if status in {'PENDING_REVIEW','CLOSED','RETURNED'} else None,
                           created_at=self.at(4), accepted_at=self.at(3) if status != 'OPEN' else None,
                           feedback_at=self.at(2) if status in {'PENDING_REVIEW','CLOSED','RETURNED'} else None,
                           closed_at=self.at(1) if status == 'CLOSED' else None)
            steps = [('DISPATCH', None, 'OPEN', owner)]
            if status != 'OPEN':steps.append(('ACCEPT','OPEN','PROCESSING',target))
            if status in {'PENDING_REVIEW','CLOSED','RETURNED'}:steps.append(('SUBMIT','PROCESSING','PENDING_REVIEW',target))
            if status in {'CLOSED','RETURNED'}:steps.append(('CLOSE' if status == 'CLOSED' else 'RETURN','PENDING_REVIEW',status,owner))
            for offset,(action,before,after,actor) in enumerate(steps):
                self.add(DeliveryEvent,f'flow-event/{index}/{offset}',delivery_id=row.id,actor_id=actor.id,
                         actor_org_id=actor.org_id,action=action,before_status=before,after_status=after,
                         note=LABEL + SOURCE,created_at=self.at(4-offset))


def seed_demo_data(db, actor, *, instant=None):
    """Caller owns the transaction. Inserts only; a completed dataset is a no-op."""
    if not actor.active or not actor.is_admin:
        raise ValueError('请选择现有启用的超级管理员作为本组织演示数据归属人')
    organization = db.get(Organization, actor.org_id)
    if not organization or not organization.active:raise ValueError('目标组织未启用')
    builder = DemoBuilder(db, actor, instant or datetime.now(timezone.utc))
    marker = builder.identity('completed')
    if db.get(Audit, marker):return {'already_present':True, 'inserted':{}, 'credentials':[]}
    builder.accounts()
    builder.cases_and_intakes()
    builder.intelligence()
    builder.persons()
    builder.places_and_water()
    builder.analysis()
    builder.ai_history()
    builder.hierarchical_deliveries()
    builder.add(Audit, 'completed', actor_id=actor.id, org_id=actor.org_id, action='DEMO_DATA_SEEDED', object_id=actor.org_id)
    db.flush()
    return {'already_present':False, 'inserted':dict(sorted(builder.counts.items())),
            'credentials':builder.credentials, 'dataset':DATASET, 'organization':organization.name,
            'owner':actor.username, 'as_of':builder.instant.isoformat()}
