"""Fixed permission catalog and fail-closed server route mapping."""
import json
from .access_models import Role

RESOURCE_NAMES={"intake":"接警信息","cases":"案件管理","evidence":"证物管理","intelligence":"情报线索","persons":"人员档案","wastewater":"污水监测"}
CATALOG=[]
for resource,name in RESOURCE_NAMES.items():
    CATALOG.extend([{"code":resource+".read","name":name+"查询","group":name},{"code":resource+".write","name":name+"办理与修改","group":name}])
CATALOG += [{"code":code,"name":name,"group":group} for code,name,group in [
    ("intake.import","导入接警Excel","接警信息"),("intake.export","导出接警信息","接警信息"),("intake.hide","隐藏接警信息","接警信息"),
    ("intake.restore","恢复接警信息（超级管理员）","接警信息"),("cases.import","批量导入案件CSV","案件管理"),("audit.read","查看本人操作记录","审计"),
    ("system.users","管理本组织普通账号","系统管理"),("system.roles","配置角色（超级管理员）","系统管理"),
    ("system.organizations","配置组织（超级管理员）","系统管理"),("system.audit","查看系统日志（超级管理员）","系统管理")]]
CODES=frozenset(item["code"] for item in CATALOG)
LEGACY_PERMISSIONS=frozenset(code for code in CODES if not code.startswith("system.") and code!="intake.restore")
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
        return {"system."+segment} if segment in {"users","roles","organizations"} else set()
    if path.startswith("/api/admin/"): return {"system.audit"} if path.endswith("audit/search") else set()
    if path=="/api/audit/mine": return {"audit.read"}
    if path=="/api/ai/status": return set()
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
    for prefix,resource in (("/api/evidence","evidence"),("/api/intelligence","intelligence"),("/api/person-drafts","persons"),("/api/wastewater","wastewater")):
        if path==prefix or path.startswith(prefix+"/"):
            required={resource+".read"} | ({resource+".write"} if method!="GET" and not path.endswith("/search") else set())
            if 'case-links' in path or 'case-candidates' in path:required.add('cases.read')
            return required
    return {"__unmapped_route__"}


def identity_json(db,user,organization):
    role=db.get(Role,user.role_id or DEFAULT_ROLE_ID) if not user.is_admin else None
    return {"username":user.username,"organization":organization.name if organization else "","organization_id":user.org_id,
        "is_admin":user.is_admin,"permissions":sorted(effective_permissions(db,user)),"role_name":"超级管理员" if user.is_admin else role.name if role else "历史业务用户"}
