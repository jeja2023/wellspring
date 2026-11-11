"""Small declarative schemas and bounded sample checks; never execute submitted code."""
from decimal import Decimal,InvalidOperation
import json

CATEGORIES={'PROJECT':{'DATASET','ENTITY','RELATION'},'MODEL':{'COLLISION','SCORE','FLOW'},'TACTIC':{'CLUE','CASE','COMPREHENSIVE'}}
OPERATORS={'eq','ne','gt','gte','lt','lte','contains','in'}


def field_name(value):
    return isinstance(value,str) and 1<=len(value)<=80 and not any(ord(char)<32 for char in value)


def conditions_valid(rows,score=False):
    if not isinstance(rows,list) or not 1<=len(rows)<=50:raise ValueError('规则条件应为 1—50 项')
    points=0
    for item in rows:
        if not isinstance(item,dict) or not field_name(item.get('field')) or item.get('operator') not in OPERATORS or 'value' not in item:raise ValueError('每项规则须包含 field、operator 和 value')
        value=item['value']
        if item['operator']=='in':
            if not isinstance(value,list) or not 1<=len(value)<=50 or any(not isinstance(v,(str,int,float,bool,type(None))) for v in value):raise ValueError('in 条件的 value 应为 1—50 项标量数组')
        elif not isinstance(value,(str,int,float,bool,type(None))):raise ValueError('条件值应为文字、数字、布尔值或空值')
        if score:
            if type(item.get('points')) is not int or not 0<=item['points']<=100:raise ValueError('每项分值须为 0—100 的整数')
            points+=item['points']
    if score and points>100:raise ValueError('规则总分不能超过 100')


def validate_config(kind,category,config):
    if category not in CATEGORIES[kind]:raise ValueError('分类不属于当前页面')
    if len(json.dumps(config,ensure_ascii=False,allow_nan=False))>20000:raise ValueError('配置内容不能超过 20000 字符')
    if kind=='PROJECT':
        fields=config.get('fields')
        if not isinstance(fields,list) or not 1<=len(fields)<=50:raise ValueError('字段结构须包含 1—50 个 fields')
        names=set()
        for item in fields:
            if not isinstance(item,dict) or not field_name(item.get('name')) or item.get('type') not in {'text','number','date','boolean'}:raise ValueError('字段须包含 name 和 type（text/number/date/boolean）')
            if item['name'] in names:raise ValueError('字段名称不能重复')
            if 'required' in item and type(item['required']) is not bool:raise ValueError('字段 required 须为布尔值')
            names.add(item['name'])
    elif kind=='MODEL':
        if category=='COLLISION':
            if config.get('mode','all') not in {'all','any'}:raise ValueError('匹配模式为 all 或 any')
            conditions_valid(config.get('conditions'))
        elif category=='SCORE':conditions_valid(config.get('rules'),True)
        else:
            steps=config.get('steps')
            if not isinstance(steps,list) or not 1<=len(steps)<=20 or any(not isinstance(step,dict) or not field_name(step.get('name')) or not isinstance(step.get('description',''),str) or len(step.get('description',''))>1000 for step in steps):raise ValueError('分析流程须包含 1—20 个步骤，每步填写 name 和 description')
    else:
        if not isinstance(config.get('steps'),str) or not config['steps'].strip() or len(config['steps'])>10000:raise ValueError('请填写 1—10000 字符的技战法操作步骤')
        if not isinstance(config.get('applicability',''),str) or len(config.get('applicability',''))>2000:raise ValueError('适用场景不能超过 2000 字符')


def matches(record,rule):
    value=record.get(rule['field']);expected=rule['value'];op=rule['operator']
    if rule['field'] not in record:return False
    if op=='eq':return type(value)==type(expected) and value==expected
    if op=='ne':return type(value)!=type(expected) or value!=expected
    if op=='contains':return isinstance(value,str) and isinstance(expected,str) and expected in value
    if op=='in':return any(type(value)==type(item) and value==item for item in expected)
    try:
        if isinstance(value,bool) or isinstance(expected,bool) or not isinstance(value,(int,float,str)) or not isinstance(expected,(int,float,str)):return False
        left,right=Decimal(str(value)),Decimal(str(expected))
        if not left.is_finite() or not right.is_finite():return False
        return {'gt':left>right,'gte':left>=right,'lt':left<right,'lte':left<=right}[op]
    except (InvalidOperation,ValueError,KeyError):return False


def sample_check(category,config,records):
    if len(json.dumps(records,ensure_ascii=False,allow_nan=False))>20000:raise ValueError('样例不能超过 20000 字符')
    if category=='FLOW':return {'mode':'FLOW','steps':[{'number':index+1,**step} for index,step in enumerate(config['steps'])],'message':'流程结构校验通过；这里只预览步骤，不执行数据任务。'}
    output=[]
    rules=config['conditions'] if category=='COLLISION' else config['rules']
    required={rule['field'] for rule in rules}
    for index,record in enumerate(records):
        if len(record)>50:raise ValueError('单条样例最多 50 个字段')
        missing=sorted(required-record.keys())
        matched=[matches(record,rule) for rule in rules]
        row={'row':index+1,'missing_fields':missing}
        if category=='SCORE':row['score']=None if missing else sum(rule['points'] for rule,hit in zip(rules,matched) if hit)
        else:row['matched']=False if missing else (all(matched) if config.get('mode','all')=='all' else any(matched))
        output.append(row)
    return {'mode':category,'rows':output,'total':len(output),'message':'仅对手工样例验证规则，不读取业务明细或作出个人认定。'}
