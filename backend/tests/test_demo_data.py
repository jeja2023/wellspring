"""Check real page queries, fixture ownership, retry and rollback safety."""
from datetime import date, timedelta
import json

import pytest
from sqlalchemy import func, select, text
from wellspring.db import Base
from wellspring.demo_data import DemoBuilder, seed_demo_data
from wellspring.models import (Audit, Case, CaseInformation, Organization, PersonDraft,
                               User, now)
from wellspring.person_models import PersonRecord
from wellspring.wastewater_models import WastewaterResult, WastewaterSite
from wellspring.ai_models import AiRun
from wellspring.access_models import Role
from test_workflow import context, auth, headers


def prepare(factory):
    with factory() as db:
        actor = db.scalar(select(User).where(User.username == 'alice'))
        actor.is_admin = True
        db.add(Case(org_id=actor.org_id, number='EXISTING', title='保留已有记录'))
        db.commit()
        return actor.id


def snapshot(db):
    return {table.name:db.execute(table.select().order_by(*table.primary_key.columns)).mappings().all()
            for table in Base.metadata.sorted_tables}


def test_demo_seed_is_additive_repeatable_and_rollbackable(context):
    _, factory = context
    actor_id = prepare(factory)
    with factory() as db:
        before = snapshot(db)
        result = seed_demo_data(db, db.get(User, actor_id))
        assert result['inserted']['wastewater_samples'] == 84
        assert result['inserted']['ai_runs'] == 24
        assert len(result['credentials']) == 6
        assert len({item['password'] for item in result['credentials']}) == 6
        assert all(len(item['password']) >= 12 for item in result['credentials'])
        assert db.execute(text('PRAGMA foreign_key_check')).all() == []
        # Existing records, account hashes, organization types and role grants stay intact.
        after = snapshot(db)
        for table in before:
            for row in before[table]:assert row in after[table]
        db.commit()
        saved = snapshot(db)
        replay = seed_demo_data(db, db.get(User,actor_id))
        assert replay == {'already_present':True,'inserted':{},'credentials':[]}
        assert snapshot(db) == saved
    with factory() as db:
        bob = db.scalar(select(User).where(User.username == 'bob'));bob.is_admin = True;db.commit()
        before = snapshot(db)
        seed_demo_data(db, bob)
        db.rollback()
        assert snapshot(db) == before


def test_demo_pages_and_detail_queries_have_valid_data(context):
    client, factory = context
    actor_id = prepare(factory)
    with factory() as db:
        report = seed_demo_data(db, db.get(User, actor_id));db.commit()
        assert db.scalar(select(func.count()).select_from(PersonRecord).where(PersonRecord.verification_status=='VERIFIED')) > 0
        assert not db.scalars(select(PersonRecord).where(PersonRecord.created_by==PersonRecord.verified_by)).all()
        actor = db.get(User,actor_id)
        builder = DemoBuilder(db,actor,now())
        person_id=builder.identity('person/0');place_id=builder.identity('place/0')
        case_id=builder.identity('case/0');clue_id=builder.identity('clue/0')
        water_id=builder.identity('water-site/0')
        analysis_id=builder.identity('analysis/MODEL/0')
        run_id=builder.identity('ai-run/0')
    login=auth(client,'alice')
    get_paths=['/cases','/intelligence/clues','/intelligence/tasks/mine','/intelligence/tasks/reviewable',
               '/imports/case-batches','/person-drafts/transfers/inbox','/ai/runs',
               f'/person-drafts/{person_id}',f'/person-drafts/{person_id}/tasks',
               f'/person-drafts/{person_id}/history',f'/person-drafts/{person_id}/case-candidates',
               f'/cases/{case_id}/relations',f'/cases/{case_id}/intake-sources',
               f'/intelligence/clues/{clue_id}/detail',f'/places/{place_id}',
               f'/places/{place_id}/inspections',f'/places/{place_id}/incidents',f'/places/{place_id}/history',
               f'/analysis/models/{analysis_id}', f'/ai/runs/{run_id}']
    for path in get_paths:
        response=client.get('/api'+path,headers=login)
        assert response.status_code==200,(path,response.text)
        if 'items' in response.json():assert response.json()['items'],path
    for kind in ['USE','CASE','MEASURE','TEST','FOLLOWUP']:
        response=client.get(f'/api/person-drafts/{person_id}/records?kind={kind}',headers=login)
        assert response.status_code==200 and response.json()['items'],(kind,response.text)
    for path in ['/case-information/search','/person-drafts/search','/places/search',
                 '/wastewater/sites/search','/wastewater/samples/search','/wastewater/results/search',
                 '/analysis/modeling/search','/analysis/models/search','/analysis/tactics/search',
                 '/system/users/search','/system/roles/search','/system/organizations/search','/geography/search','/geography/points']:
        response=client.post('/api'+path,headers=login,json={})
        assert response.status_code==200 and response.json()['items'],(path,response.text)
    for days in [7,30,90]:
        response=client.get(f'/api/dashboard/overview?days={days}',headers=login)
        assert response.status_code==200
        assert all(metric['total']>0 and metric['period_count']>0 for metric in response.json()['metrics'])
        assert all(any(series['values']) for series in response.json()['trend']['series'])
    trend=client.post('/api/wastewater/trends/search',headers=login,json={
        'site_id':water_id,'analyte':'甲基苯丙胺','laboratory':'【演示】清源测试实验室',
        'analysis_method':'LC-MS/MS（演示）','sampling_method':'COMPOSITE',
        'start_date':(date.today()-timedelta(days=30)).isoformat(),'end_date':date.today().isoformat()})
    assert trend.status_code==200 and len(trend.json()['points'])==14,trend.text
    run=client.get('/api/ai/runs/'+run_id,headers=login).json()
    assert '未调用模型' in run['output_text']
    # A distinct actor can actually process a pending result using normal APIs.
    with factory() as db:
        result=db.scalar(select(WastewaterResult).where(WastewaterResult.org_id==db.get(User,actor_id).org_id,WastewaterResult.state=='DRAFT'))
        identity,version=result.id,result.version
    reviewed=client.post(f'/api/wastewater/results/{identity}/review',headers=headers(login),json={'version':version,'action':'CONFIRM','note':'验证预置记录可继续办理'})
    assert reviewed.status_code==200,reviewed.text
    # Existing outsider sees none of the target organization's fixtures.
    outsider=auth(client,'bob')
    assert client.get('/api/cases',headers=outsider).json()['total']==0
    assert client.get('/api/ai/runs/'+run_id,headers=outsider).status_code==404
    # Demo branch account has valid incoming and outgoing flows without altering the owner's hierarchy.
    credentials=next(item for item in report['credentials'] if 'demo_branch_' in item['username'])
    response=client.post('/api/login',json={'username':credentials['username'],'password':credentials['password']})
    assert response.status_code==200,response.text
    flow_headers={'Authorization':'Bearer '+response.json()['token']}
    for scope in ['received','sent']:
        response=client.post('/api/intelligence/deliveries/search',headers=flow_headers,json={'scope':scope})
        assert response.status_code==200 and response.json()['total']==5,response.text


def test_non_admin_cannot_be_used_as_demo_owner(context):
    _,factory=context
    with factory() as db:
        actor=db.scalar(select(User).where(User.username=='alice'))
        before=snapshot(db)
        with pytest.raises(ValueError,match='超级管理员'):seed_demo_data(db,actor)
        assert snapshot(db)==before
