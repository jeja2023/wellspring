"""Versioned administration, serialized changes, least-privilege delegation."""
import hashlib
import json
from typing import Literal
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from .access_models import Role, AdministrationLock
from .access_policy import CATALOG, CODES, effective_permissions
from .db import get_db
from .models import Organization, User, Session as LoginSession
from .security import current_user, password_hash, verify_password


class Input(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)


class Search(Input):
    keyword:str=Field(default="",max_length=100)
    page:int=Field(default=1,ge=1,le=100000)
    page_size:int=Field(default=20,ge=1,le=100)


class UserFields(Input):
    org_id:str=Field(min_length=1,max_length=36)
    role_id:str|None=Field(default=None,min_length=1,max_length=36)
    active:bool=True
    is_admin:bool=False


class UserCreate(UserFields):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=False)
    username:str=Field(min_length=1,max_length=80,pattern=r"^[A-Za-z0-9_.@-]+$")
    password:str=Field(min_length=12,max_length=256)


class UserUpdate(UserFields):
    version:int=Field(ge=1)


class Reset(Input):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=False)
    version:int=Field(ge=1)
    password:str=Field(min_length=12,max_length=256)


class ChangePassword(Input):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=False)
    old_password:str=Field(min_length=1,max_length=256)
    password:str=Field(min_length=12,max_length=256)


class RoleFields(Input):
    name:str=Field(min_length=1,max_length=120)
    kind:Literal["USER","ADMIN"]="USER"
    description:str=Field(default="",max_length=1000)
    permissions:list[str]=Field(default_factory=list,max_length=100)
    active:bool=True

    @model_validator(mode="after")
    def permitted(self):
        codes=set(self.permissions)
        if not codes<=CODES: raise ValueError("包含未注册权限")
        reserved={"system.roles","system.organizations","system.audit","intake.restore"}
        if codes&reserved: raise ValueError("此类权限仅保留给超级管理员")
        if self.kind=="USER" and any(code.startswith("system.") for code in codes): raise ValueError("普通用户角色不能包含系统管理权限")
        for code in codes:
            resource=code.split(".")[0]
            if resource not in {"system","audit"} and not code.endswith(".read") and resource+".read" not in codes:
                raise ValueError("操作权限必须同时授予对应查询权限")
        if "intake.write" in codes and "cases.write" in codes and "cases.read" not in codes: raise ValueError("需案件查询权限")
        self.permissions=sorted(codes)
        return self


class RoleCreate(RoleFields):
    code:str=Field(min_length=1,max_length=80,pattern=r"^[a-z][a-z0-9_]*$")


class RoleUpdate(RoleFields):
    version:int=Field(ge=1)


class OrganizationFields(Input):
    name:str=Field(min_length=1,max_length=120)
    parent_id:str|None=Field(default=None,min_length=1,max_length=36)
    active:bool=True


class OrganizationUpdate(OrganizationFields):
    version:int=Field(ge=1)


def user_json(db,row):
    org=db.get(Organization,row.org_id);role=db.get(Role,row.role_id) if row.role_id else None
    return {"id":row.id,"username":row.username,"org_id":row.org_id,"organization":org.name if org else "",
        "role_id":row.role_id,"role_name":"超级管理员" if row.is_admin else role.name if role else "历史业务用户",
        "kind":"SUPER" if row.is_admin else role.kind if role else "USER","active":row.active,"is_admin":row.is_admin,"version":row.version}


def role_json(row):
    return {"id":row.id,"code":row.code,"name":row.name,"kind":row.kind,"description":row.description,"active":row.active,
            "permissions":json.loads(row.permissions_json),"version":row.version}


def organization_json(row):
    return {"id":row.id,"name":row.name,"parent_id":row.parent_id,"active":row.active,"version":row.version}


def create_router(error,audit,reserve,finish,page_result,request_id):
    router=APIRouter(prefix="/api",tags=["系统管理"])

    def require(db,user,permission,super_only=False):
        if not user.is_admin and (super_only or permission not in effective_permissions(db,user)):
            raise error(403,"FORBIDDEN","当前账号无此管理权限")

    def lock(db,user,permission,super_only=False):
        dialect=db.get_bind().dialect.name
        if dialect in {"sqlite","postgresql"}:
            if dialect=="sqlite": from sqlalchemy.dialects.sqlite import insert
            else: from sqlalchemy.dialects.postgresql import insert
            db.execute(insert(AdministrationLock).values(id="accounts",version=1).on_conflict_do_nothing(index_elements=["id"]))
        db.execute(update(AdministrationLock).where(AdministrationLock.id=="accounts").values(version=AdministrationLock.version+1))
        db.expire_all();db.refresh(user)
        if not user.active: raise error(401,"UNAUTHENTICATED","账号已停用")
        if not db.get(LoginSession,getattr(user,"_authenticated_session","")):
            raise error(401,"UNAUTHENTICATED","会话已撤销，请重新登录")
        organization_for(db,user.org_id)
        require(db,user,permission,super_only)

    def role_for(db,user,role_id,is_admin):
        if is_admin:
            if not user.is_admin: raise error(403,"FORBIDDEN","不能授予超级管理员")
            return None
        role=db.get(Role,role_id) if role_id else None
        if not role or not role.active: raise error(422,"INVALID_ROLE","请选择启用的角色")
        if not user.is_admin and (role.kind!="USER" or not set(json.loads(role.permissions_json))<=effective_permissions(db,user)):
            raise error(403,"FORBIDDEN","不能分配超出自身权限的角色")
        return role.id

    def organization_for(db,identity):
        row=db.get(Organization,identity)
        if not row or not row.active: raise error(422,"INVALID_ORGANIZATION","请选择启用的组织")
        return row

    def target_user(db,actor,identity):
        row=db.get(User,identity)
        if not row: raise error(404,"NOT_FOUND","账号不存在或无权管理")
        if not actor.is_admin:
            role=db.get(Role,row.role_id) if row.role_id else None
            if row.org_id!=actor.org_id or row.is_admin or (role and role.kind!="USER"):
                raise error(403,"FORBIDDEN","仅能管理本组织普通账号")
        return row

    def paged(db,stmt,data,render,request):
        total=db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        rows=db.scalars(stmt.offset((data.page-1)*data.page_size).limit(data.page_size)).all()
        return page_result([render(row) for row in rows],data.page,data.page_size,total,request_id(request))

    def store(db,user,record,result,code,action,identity):
        audit(db,user,action,identity);finish(record,result,code,identity);db.commit();return result

    @router.get("/system/catalog")
    def catalog(user:User=Depends(current_user),db:Session=Depends(get_db)):
        require(db,user,"system.users")
        audit(db,user,"PERMISSION_CATALOG_VIEW",user.id);db.commit()
        return {"items":CATALOG,"super_only":["system.roles","system.organizations","system.audit","intake.restore"]}

    @router.get("/system/options")
    def options(user:User=Depends(current_user),db:Session=Depends(get_db)):
        require(db,user,"system.users")
        roles=db.scalars(select(Role).order_by(Role.name).limit(1001)).all()
        if not user.is_admin: roles=[row for row in roles if row.kind=="USER" and set(json.loads(row.permissions_json))<=effective_permissions(db,user)]
        orgs=db.scalars(select(Organization).where(True if user.is_admin else Organization.id==user.org_id).order_by(Organization.name).limit(1001)).all()
        if len(roles)>1000 or len(orgs)>1000: raise error(422,"OPTIONS_TOO_LARGE","组织或角色超过1000条，请先收敛配置")
        return {"roles":[role_json(row) for row in roles],"organizations":[organization_json(row) for row in orgs]}

    @router.post("/system/users/search")
    def users(data:Search,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        require(db,user,"system.users")
        stmt=select(User).order_by(User.username)
        if not user.is_admin:
            stmt=stmt.outerjoin(Role,User.role_id==Role.id).where(User.org_id==user.org_id,User.is_admin.is_(False),or_(User.role_id.is_(None),Role.kind=="USER"))
        if data.keyword: stmt=stmt.where(User.username.contains(data.keyword,autoescape=True))
        result=paged(db,stmt,data,lambda row:user_json(db,row),request)
        audit(db,user,"USER_LIST",user.id);db.commit();return result

    @router.post("/system/users",status_code=201)
    def create_user(data:UserCreate,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        lock(db,user,"system.users")
        if not user.is_admin and data.org_id!=user.org_id: raise error(403,"FORBIDDEN","只能创建本组织账号")
        organization_for(db,data.org_id);role_id=role_for(db,user,data.role_id,data.is_admin)
        payload=data.model_dump(exclude={"password"});payload["password_digest"]=hashlib.sha256(data.password.encode()).hexdigest()
        record,replay=reserve(db,user,"USER_CREATE",key,payload)
        if replay:return replay
        if db.scalar(select(User.id).where(User.username==data.username)): raise error(409,"USERNAME_EXISTS","账号已存在")
        row=User(username=data.username,password_hash=password_hash(data.password),org_id=data.org_id,role_id=role_id,active=data.active,is_admin=data.is_admin)
        db.add(row);db.flush()
        return store(db,user,record,user_json(db,row),201,"USER_CREATE",row.id)

    @router.post("/system/users/{identity}/update")
    def update_user(identity:str,data:UserUpdate,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        lock(db,user,"system.users");row=target_user(db,user,identity)
        if not user.is_admin and data.org_id!=user.org_id: raise error(403,"FORBIDDEN","不能迁移账号组织")
        organization_for(db,data.org_id);role_id=role_for(db,user,data.role_id,data.is_admin)
        record,replay=reserve(db,user,"USER_UPDATE",key,{"id":identity,**data.model_dump()})
        if replay:return replay
        if row.version!=data.version:raise error(409,"VERSION_CONFLICT","账号已变化，请重新查询")
        if row.is_admin and row.active and (not data.is_admin or not data.active):
            remaining=db.scalar(select(func.count()).select_from(User).join(Organization,User.org_id==Organization.id).where(User.id!=identity,User.is_admin.is_(True),User.active.is_(True),Organization.active.is_(True)))
            if not remaining:raise error(409,"LAST_ADMIN","必须保留至少一个可登录的超级管理员")
        for name,value in {"org_id":data.org_id,"role_id":role_id,"active":data.active,"is_admin":data.is_admin,"version":row.version+1}.items():setattr(row,name,value)
        db.execute(delete(LoginSession).where(LoginSession.user_id==identity))
        return store(db,user,record,user_json(db,row),200,"USER_UPDATE",identity)

    @router.post("/system/users/{identity}/password")
    def reset(identity:str,data:Reset,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        lock(db,user,"system.users");row=target_user(db,user,identity)
        record,replay=reserve(db,user,"USER_PASSWORD_RESET",key,{"id":identity,"version":data.version,"password_digest":hashlib.sha256(data.password.encode()).hexdigest()})
        if replay:return replay
        if row.version!=data.version:raise error(409,"VERSION_CONFLICT","账号已变化，请重新查询")
        row.password_hash=password_hash(data.password);row.version+=1
        db.execute(delete(LoginSession).where(LoginSession.user_id==identity))
        return store(db,user,record,{"id":identity,"version":row.version},200,"USER_PASSWORD_RESET",identity)

    @router.post("/account/password")
    def change(data:ChangePassword,user:User=Depends(current_user),db:Session=Depends(get_db)):
        if not verify_password(data.old_password,user.password_hash):raise error(403,"INVALID_PASSWORD","原密码不正确")
        changed=db.execute(update(User).where(User.id==user.id,User.version==user.version,User.active.is_(True)).values(password_hash=password_hash(data.password),version=User.version+1))
        if changed.rowcount!=1:raise error(409,"VERSION_CONFLICT","账号已变化，请重新登录后修改密码")
        db.execute(delete(LoginSession).where(LoginSession.user_id==user.id));audit(db,user,"PASSWORD_CHANGE",user.id);db.commit();return {"ok":True}

    @router.post("/system/roles/search")
    def roles(data:Search,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        require(db,user,"system.roles",True)
        stmt=select(Role).order_by(Role.name)
        if data.keyword:stmt=stmt.where(or_(Role.name.contains(data.keyword,autoescape=True),Role.code.contains(data.keyword,autoescape=True)))
        result=paged(db,stmt,data,role_json,request);audit(db,user,"ROLE_LIST",user.id);db.commit();return result

    def save_role(identity,data,user,db,key):
        lock(db,user,"system.roles",True)
        record,replay=reserve(db,user,"ROLE_SAVE",key,{"id":identity,**data.model_dump()})
        if replay:return replay
        if identity:
            row=db.get(Role,identity)
            if not row:raise error(404,"NOT_FOUND","角色不存在")
            if row.version!=data.version:raise error(409,"VERSION_CONFLICT","角色已变化，请重新查询")
            row.version+=1
        else:
            if db.scalar(select(Role.id).where(Role.code==data.code)):raise error(409,"ROLE_EXISTS","角色代码已存在")
            row=Role(code=data.code);db.add(row)
        for field in ("name","kind","description","active"):setattr(row,field,getattr(data,field))
        row.permissions_json=json.dumps(data.permissions);db.flush()
        assigned=User.is_admin.is_(False) & ((User.role_id==row.id) | (User.role_id.is_(None) if row.code=="business_user" else False))
        db.execute(update(User).where(assigned).values(version=User.version+1))
        db.execute(delete(LoginSession).where(LoginSession.user_id.in_(select(User.id).where(assigned))))
        return store(db,user,record,role_json(row),200 if identity else 201,"ROLE_SAVE",row.id)

    @router.post("/system/roles",status_code=201)
    def create_role(data:RoleCreate,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        return save_role(None,data,user,db,key)

    @router.post("/system/roles/{identity}/update")
    def update_role(identity:str,data:RoleUpdate,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        return save_role(identity,data,user,db,key)

    @router.post("/system/organizations/search")
    def organizations(data:Search,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
        require(db,user,"system.organizations",True)
        stmt=select(Organization).order_by(Organization.name)
        if data.keyword:stmt=stmt.where(Organization.name.contains(data.keyword,autoescape=True))
        result=paged(db,stmt,data,organization_json,request);audit(db,user,"ORGANIZATION_LIST",user.id);db.commit();return result

    def save_organization(identity,data,user,db,key):
        lock(db,user,"system.organizations",True)
        record,replay=reserve(db,user,"ORGANIZATION_SAVE",key,{"id":identity,**data.model_dump()})
        if replay:return replay
        if data.parent_id:
            parent=organization_for(db,data.parent_id);visited=set()
            while parent:
                if parent.id==identity or parent.id in visited:raise error(409,"ORGANIZATION_CYCLE","上级组织不能形成循环")
                visited.add(parent.id);parent=db.get(Organization,parent.parent_id) if parent.parent_id else None
        if db.scalar(select(Organization.id).where(Organization.name==data.name,Organization.id!=(identity or ""))):raise error(409,"ORGANIZATION_EXISTS","组织名称已存在")
        row=db.get(Organization,identity) if identity else Organization()
        if identity and not row:raise error(404,"NOT_FOUND","组织不存在")
        if identity and row.version!=data.version:raise error(409,"VERSION_CONFLICT","组织已变化，请重新查询")
        if identity and not data.active:
            if db.scalar(select(User.id).where(User.org_id==identity,User.active.is_(True)).limit(1)) or db.scalar(select(Organization.id).where(Organization.parent_id==identity,Organization.active.is_(True)).limit(1)):
                raise error(409,"ORGANIZATION_IN_USE","请先处理启用中的直属用户和下级组织，再停用组织")
        if identity:row.version+=1
        else:db.add(row)
        row.name=data.name;row.parent_id=data.parent_id;row.active=data.active;db.flush()
        return store(db,user,record,organization_json(row),200 if identity else 201,"ORGANIZATION_SAVE",row.id)

    @router.post("/system/organizations",status_code=201)
    def create_organization(data:OrganizationFields,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        return save_organization(None,data,user,db,key)

    @router.post("/system/organizations/{identity}/update")
    def update_organization(identity:str,data:OrganizationUpdate,user:User=Depends(current_user),db:Session=Depends(get_db),key:str|None=Header(None,alias="Idempotency-Key")):
        return save_organization(identity,data,user,db,key)

    return router
