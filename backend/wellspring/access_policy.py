"""Fixed permission catalog and fail-closed server route mapping."""
import json
from .access_models import Role

RESOURCE_NAMES={"intake":"接警信息","cases":"案件管理","intelligence":"情报线索","persons":"人员档案","wastewater":"污水监测","modeling":"数据建模","models":"模型管理","tactics":"技战法库"}
CATALOG=[]
for resource,name in RESOURCE_NAMES.items():
    CATALOG.extend([{"code":resource+".read","name":name+"查询","group":name},{"code":resource+".write","name":name+"办理与修改","group":name}])
CATALOG += [{"code":code,"name":name,"group":group} for code,name,group in [
    ("intake.import","导入接警Excel","接警信息"),("intake.export","导出接警信息","接警信息"),("intake.hide","隐藏接警信息","接警信息"),
    ("intake.restore","恢复接警信息（超级管理员）","接警信息"),("cases.import","批量导入案件CSV","案件管理"),("audit.read","查看本人操作记录","审计"),
    ("system.users","管理本组织普通账号","系统管理"),("system.roles","配置角色（超级管理员）","系统管理"),
    ("system.organizations","配置组织（超级管理员）","系统管理"),("system.audit","查看系统日志（超级管理员）","系统管理"),
    ("persons.identity","查看完整身份信息","人员档案"),("persons.health","查看敏感业务资料","人员档案"),
    ("persons.verify","核验人员与业务记录","人员档案"),("persons.use","登记吸毒相关记录","人员档案"),
    ("persons.cases","维护正式案件关系","人员档案"),("persons.treatment","维护戒毒措施","人员档案"),
    ("persons.followup","维护检测随访","人员档案"),("persons.transfer","办理人员责任移交","人员档案"),
    ("dashboard.read","数据大屏查询","数据大屏"),("ai.read","智能研判查询","智能研判"),
    ("intelligence.import","导入情报线索","情报线索"),("intelligence.dispatch","下发情报线索","情报线索"),
    ("intelligence.dispose","处置及反馈线索","情报线索"),("intelligence.review","复核办结线索","情报线索"),
    ("ai.generate","使用大模型生成草稿","智能研判"),("system.ai","配置模型服务（超级管理员）","系统管理")]]
CATALOG += [{"code":code,"name":name,"group":group} for code,name,group in [
    ("places.read","查询场所、巡查及事件","重点场所"),("places.write","维护场所、巡查及事件","重点场所"),
    ("places.review","核验场所事件及复核办结","重点场所"),
    ("geography.read","查看获准业务图层","业务地图"),("geography.write","维护获准业务坐标","业务地图")]]
CODES=frozenset(item["code"] for item in CATALOG)
LEGACY_PERMISSIONS=frozenset(code for code in CODES if not code.startswith(("system.","places.","geography.")) and code not in {"intake.restore","ai.generate","persons.identity","persons.health","persons.verify","persons.use","persons.cases","persons.treatment","persons.followup","persons.transfer"})
DEFAULT_ROLE_ID="wellspring-business-user"


def effective_permissions(db,user):
    if user.is_admin: return set(CODES)
    if user.role_id is None:
        # Old CLI users follow the managed compatibility role once it exists;
        # disabling that role must not be bypassed by a NULL assignment.
        role=db.get(Role,DEFAULT_ROLE_ID)
        if role is None:return set()
    else:role=db.get(Role,user.role_id)
    if not role or not role.active: return set()
    try: return set(json.loads(role.permissions_json)) & CODES
    except (ValueError,TypeError): return set()


def route_permissions(method,path):
    if path in {"/api/session","/api/logout","/api/account/password"}: return set()
    if path.startswith("/api/system/"):
        segment=path.removeprefix("/api/system/").split("/")[0]
        return {"system."+segment} if segment in {"users","roles","organizations","ai"} else set()
    if path.startswith("/api/admin/"): return {"system.audit"} if path.endswith("audit/search") else set()
    if path=="/api/audit/mine": return {"audit.read"}
    if path=="/api/dashboard/overview": return {"dashboard.read"}
    if path.startswith("/api/ai/"):
        if path=="/api/ai/status" or (path=="/api/ai/runs" and method=="GET") or path.startswith("/api/ai/runs/"):
            return {"ai.read"}
        if path=="/api/ai/runs" and method=="POST":return {"ai.read","ai.generate"}
        return {"__unmapped_route__"}
    if path.startswith('/api/geography/'):
        return {'geography.read'} | ({'geography.write'} if path.endswith('/location') else set())
    if path == '/api/places' or path.startswith('/api/places/'):
        if path.endswith('/transition'): return {'places.read'}  # Action-specific checks under the administration lock.
        required={'places.read'} | ({'places.write'} if method!='GET' and not path.endswith('/search') else set())
        if path.endswith('/clue'): required |= {'intelligence.read','intelligence.write'}
        return required
    if path.startswith("/api/analysis/"):
        area=path.removeprefix("/api/analysis/").split("/")[0]
        if area not in {"modeling","models","tactics"}:return {"__unmapped_route__"}
        return {area+".read"}|({area+".write"} if method!="GET" and not path.endswith(("/search","/validate")) else set())
    if path.startswith("/api/imports/"): return {"cases.read","cases.import"}
    if path.startswith("/api/case-information"):
        if path.endswith("/case-link"): return {"intake.read","intake.write","cases.read","cases.write"}
        if path.endswith("/import"): return {"intake.read","intake.import"}
        if path.endswith("/export"): return {"intake.read","intake.export"}
        if path.endswith("/delete"): return {"intake.read","intake.hide"}
        if "/admin/" in path: return {"intake.read","intake.restore"}
        return {"intake.read"} | ({"intake.write"} if method!="GET" and not path.endswith("/search") else set())
    if path.startswith("/api/cases"):
        result={"cases.read"}
        if "intake-sources" in path: result.add("intake.read")
        if method!="GET": result.add("cases.write")
        if path.endswith("/revoke") and "intake-sources" in path: result.add("intake.write")
        return result
    if path.startswith("/api/intelligence/imports"):
        return {"intelligence.read","intelligence.import"}
    if path.startswith("/api/intelligence/"):
        action=path.rsplit("/",1)[-1]
        if action in {"dispatch","redispatch"}:return {"intelligence.read","intelligence.dispatch"}
        if action=='reassign' and '/deliveries/' in path:return {"intelligence.read","intelligence.dispatch"}
        if action in {"accept","progress","feedback"}:return {"intelligence.read","intelligence.dispose"}
        if action=="resolve":return {"intelligence.read","intelligence.review"}
    if path.startswith("/api/person-drafts/"):
        action=path.rsplit('/',1)[-1]
        if action in {'identity-review','review'}:return {'persons.read','persons.verify'}
        if action in {'execute'}:return {'persons.read','persons.treatment'}
        if '/transfers' in path:return {'persons.read','persons.transfer'}
        if '/tasks' in path:return {'persons.read','persons.health'}
        if '/records' in path or action=='history':return {'persons.read'}
    for prefix,resource in (("/api/intelligence","intelligence"),("/api/person-drafts","persons"),("/api/wastewater","wastewater")):
        if path==prefix or path.startswith(prefix+"/"):
            required={resource+".read"} | ({resource+".write"} if method!="GET" and not path.endswith("/search") else set())
            if 'case-links' in path or 'case-candidates' in path:required.add('cases.read')
            return required
    return {"__unmapped_route__"}


def identity_json(db,user,organization):
    role=db.get(Role,user.role_id or DEFAULT_ROLE_ID) if not user.is_admin else None
    return {"username":user.username,"organization":organization.name if organization else "","organization_id":user.org_id,
        "is_admin":user.is_admin,"permissions":sorted(effective_permissions(db,user)),"role_name":"超级管理员" if user.is_admin else role.name if role else "历史业务用户"}
