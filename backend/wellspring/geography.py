"""Bounded, permission-scoped maps of facilities and incident locations only."""
from pathlib import Path
import json
import math
import os
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import String, and_, cast, func, literal, select, union_all
from sqlalchemy.orm import Session
from .access_policy import effective_permissions
from .clue_deliveries import lock_flow
from .db import get_db
from .models import User, now
from .place_models import GeoLocation as Location, GeoLocationEvent, Place, PlaceIncident
from .security import current_user
from .wastewater_models import WastewaterSite

RESOURCE_MODELS = {'PLACE': Place, 'INCIDENT': PlaceIncident, 'WASTEWATER': WastewaterSite}
RESOURCE_PERMISSIONS = {'PLACE': 'places', 'INCIDENT': 'places', 'WASTEWATER': 'wastewater'}


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Search(Input):
    layer: Literal['ALL', 'PLACE', 'INCIDENT', 'WASTEWATER'] = 'ALL'
    keyword: str = Field(default='', max_length=100)
    located: bool | None = None
    page: int = Field(default=1, ge=1, le=100000)
    bbox: tuple[float, float, float, float] | None = None

    @model_validator(mode='after')
    def bounds(self):
        if self.bbox:
            west, south, east, north = self.bbox
            if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
                raise ValueError('查询范围无效')
        return self


class LocationInput(Input):
    version: int = Field(ge=0)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-85, le=85)
    source: str = Field(min_length=1, max_length=500)
    coordinate_system: Literal['WGS84'] = 'WGS84'

    @model_validator(mode='after')
    def pair(self):
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError('经纬度须同时填写或同时清除')
        return self


def tile_root():
    configured = os.environ.get('WELLSPRING_MAP_TILE_DIR', '').strip()
    return Path(configured).resolve() if configured else None


def tile_options():
    """Explicit deployment metadata; never infer a coordinate system from images."""
    coordinate_system = os.environ.get('WELLSPRING_MAP_TILE_CRS', 'WGS84').strip().upper()
    if coordinate_system not in {'WGS84', 'GCJ02'}:
        raise ValueError('Unsupported tile coordinate system')
    minimum = int(os.environ.get('WELLSPRING_MAP_MIN_ZOOM', '0'))
    maximum = int(os.environ.get('WELLSPRING_MAP_MAX_ZOOM', '20'))
    zoom = int(os.environ.get('WELLSPRING_MAP_INITIAL_ZOOM', '13'))
    # AMap city center for Wuxi; WGS84 value uses the same approximate offline inverse as the client.
    default_center = '120.301663,31.574729' if coordinate_system == 'GCJ02' else '120.297066,31.576634'
    longitude, latitude = map(float, os.environ.get('WELLSPRING_MAP_CENTER', default_center).split(','))
    if not (0 <= minimum <= zoom <= maximum <= 20 and math.isfinite(longitude) and math.isfinite(latitude)
            and -180 <= longitude <= 180 and -85 <= latitude <= 85):
        raise ValueError('Invalid offline map view')
    return {'tile_coordinate_system': coordinate_system, 'min_zoom': minimum, 'max_zoom': maximum,
            'initial_view': {'longitude': longitude, 'latitude': latitude, 'zoom': zoom}}


def create_router(error, audit, reserve, finish, page_result, request_id):
    router = APIRouter(prefix='/api/geography', tags=['业务地图'])

    def resource(db, user, kind, identity, writing=False):
        if kind not in RESOURCE_MODELS: raise error(404, 'NOT_FOUND', '点位类型不存在')
        prefix = RESOURCE_PERMISSIONS[kind]
        required = {prefix + '.read'} | ({prefix + '.write'} if writing else set())
        if not required <= effective_permissions(db, user): raise error(403, 'FORBIDDEN', '当前账号无此图层权限')
        model = RESOURCE_MODELS[kind]
        row = db.scalar(select(model).where(model.id == identity, model.org_id == user.org_id))
        if not row: raise error(404, 'NOT_FOUND', '点位不存在或无权访问')
        return row

    def sources(db, user, data):
        permissions = effective_permissions(db, user)
        allowed = [kind for kind, prefix in RESOURCE_PERMISSIONS.items() if prefix + '.read' in permissions]
        if data.layer != 'ALL' and data.layer not in allowed: raise error(403, 'FORBIDDEN', '当前账号无此图层权限')
        queries = []
        for kind in allowed:
            if data.layer != 'ALL' and data.layer != kind: continue
            model = RESOURCE_MODELS[kind]
            if kind == 'INCIDENT':
                name, code, address, state, place_id = model.title, literal(''), Place.address, model.status, model.place_id
            else:
                name, code = model.name, model.code
                address = model.address if kind == 'PLACE' else model.district
                state, place_id = cast(model.active, String), model.id if kind == 'PLACE' else literal(None)
            query = select(literal(kind).label('resource_type'), model.id.label('resource_id'), name.label('name'), code.label('code'),
                address.label('address'), state.label('state'), place_id.label('place_id'),
                Location.longitude, Location.latitude, func.coalesce(Location.version, 0).label('version'), func.coalesce(Location.source, '').label('source'))
            query = query.select_from(model)
            if kind == 'INCIDENT': query = query.join(Place, Place.id == model.place_id)
            query = query.outerjoin(Location, and_(Location.resource_type == kind, Location.resource_id == model.id, Location.org_id == user.org_id)).where(model.org_id == user.org_id)
            if data.keyword: query = query.where(name.contains(data.keyword, autoescape=True) | code.contains(data.keyword, autoescape=True) | address.contains(data.keyword, autoescape=True))
            queries.append(query)
        return union_all(*queries).subquery() if queries else None

    def filtered(base, data):
        query = select(base)
        if data.located is not None: query = query.where(base.c.longitude.is_not(None) if data.located else base.c.longitude.is_(None))
        if data.bbox:
            west, south, east, north = data.bbox
            query = query.where(base.c.longitude.between(west, east), base.c.latitude.between(south, north))
        return query

    @router.get('/config')
    def config(user: User = Depends(current_user), db: Session = Depends(get_db)):
        root = tile_root()
        try:
            options = tile_options()
        except (ValueError, TypeError):
            raise error(503, 'MAP_CONFIG_INVALID', '离线地图配置无效，请检查底图坐标系、级别和初始范围') from None
        return {'coordinate_system': 'WGS84', **options, 'tiles_available': bool(root and root.is_dir()),
            'attribution': os.environ.get('WELLSPRING_MAP_ATTRIBUTION', '本地授权底图')[:500],
            'layers': [kind for kind, prefix in RESOURCE_PERMISSIONS.items() if prefix + '.read' in effective_permissions(db, user)]}

    @router.post('/search')
    def search(data: Search, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        base = sources(db, user, data)
        if base is None: return page_result([], data.page, 20, 0, request_id(request))
        query = filtered(base, data)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.execute(query.order_by(base.c.resource_type, base.c.name, base.c.resource_id).offset((data.page-1)*20).limit(20)).mappings().all()
        audit(db, user, 'GEO_RESOURCE_SEARCH', user.org_id); db.commit()
        return page_result([dict(row) for row in rows], data.page, 20, total, request_id(request))

    @router.post('/points')
    def points(data: Search, user: User = Depends(current_user), db: Session = Depends(get_db)):
        base = sources(db, user, data)
        if base is None: return {'items': [], 'total': 0, 'truncated': False, 'limit': 500}
        query = filtered(base, data).where(base.c.longitude.is_not(None))
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.execute(query.order_by(base.c.resource_type, base.c.resource_id).limit(500)).mappings().all()
        audit(db, user, 'GEO_POINTS_READ', user.org_id); db.commit()
        return {'items': [dict(row) for row in rows], 'total': total, 'truncated': total > 500, 'limit': 500}

    @router.get('/tiles/{z}/{x}/{y}.png')
    def tile(z: int, x: int, y: int, user: User = Depends(current_user)):
        root = tile_root()
        if root is None or not root.is_dir() or not 0 <= z <= 20 or not 0 <= x < 2 ** z or not 0 <= y < 2 ** z:
            raise error(404, 'TILE_NOT_FOUND', '当前位置无离线底图')
        candidates = [root / str(z) / str(x) / (str(y) + '.png'), root / str(z) / str(x) / str(y) / 'tile.png']
        raw = None
        for candidate in candidates:
            try:
                path = candidate.resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    continue
                with path.open('rb') as stream:
                    raw = stream.read(2_000_001)
                break
            except OSError:
                continue
        if raw is None or len(raw) > 2_000_000:
            raise error(404, 'TILE_NOT_FOUND', '当前位置无离线底图')
        # Read the validated local bytes; never make network requests or expose paths.
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise error(404, 'TILE_NOT_FOUND', '底图文件格式不支持')
        return Response(raw, media_type='image/png', headers={'Cache-Control': 'private, no-store'})

    @router.get('/{kind}/{identity}')
    def detail(kind: str, identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = resource(db, user, kind, identity)
        location = db.scalar(select(Location).where(Location.resource_type == kind, Location.resource_id == identity, Location.org_id == user.org_id))
        return {'resource_type': kind, 'resource_id': identity, 'name': row.title if kind == 'INCIDENT' else row.name,
            'place_id': row.place_id if kind == 'INCIDENT' else row.id if kind == 'PLACE' else None,
            'longitude': location.longitude if location else None, 'latitude': location.latitude if location else None,
            'version': location.version if location else 0, 'source': location.source if location else ''}

    @router.post('/{kind}/{identity}/location')
    def locate(kind: str, identity: str, data: LocationInput, user: User = Depends(current_user), db: Session = Depends(get_db), key: str | None = Header(None, alias='Idempotency-Key')):
        lock_flow(db, user, 'geography.write', error, 'geography.read'); resource(db, user, kind, identity, True)
        record, replay = reserve(db, user, 'GEO_LOCATION', key, {'kind': kind, 'id': identity, **data.model_dump()})
        if replay: return replay
        location = db.scalar(select(Location).where(Location.resource_type == kind, Location.resource_id == identity, Location.org_id == user.org_id))
        if (location.version if location else 0) != data.version: raise error(409, 'VERSION_CONFLICT', '坐标已变化，请重新打开点位后修改')
        if not location:
            location = Location(org_id=user.org_id, resource_type=kind, resource_id=identity, updated_by=user.id)
            db.add(location)
        location.longitude = round(data.longitude, 6) if data.longitude is not None else None
        location.latitude = round(data.latitude, 6) if data.latitude is not None else None
        location.source = data.source; location.version = data.version + 1; location.updated_by = user.id; location.updated_at = now()
        db.flush()
        result = {'resource_type': kind, 'resource_id': identity, 'longitude': location.longitude, 'latitude': location.latitude,
            'source': location.source, 'version': location.version, 'coordinate_system': 'WGS84'}
        db.add(GeoLocationEvent(location_id=location.id, org_id=user.org_id, actor_id=user.id,
            snapshot_json=json.dumps(jsonable_encoder(result), ensure_ascii=False)))
        audit(db, user, 'GEO_LOCATION_UPDATED', location.id); finish(record, result, 200, location.id); db.commit()
        return result

    @router.get('/{kind}/{identity}/history')
    def history(kind: str, identity: str, request: Request, page: int = Query(1, ge=1, le=100000), user: User = Depends(current_user), db: Session = Depends(get_db)):
        resource(db, user, kind, identity)
        query = select(GeoLocationEvent).join(Location, Location.id == GeoLocationEvent.location_id).where(Location.resource_type == kind, Location.resource_id == identity, GeoLocationEvent.org_id == user.org_id)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(GeoLocationEvent.created_at.desc(), GeoLocationEvent.id.desc()).offset((page-1)*20).limit(20)).all()
        audit(db, user, 'GEO_HISTORY_READ', identity); db.commit()
        return page_result([{'id': row.id, 'created_at': row.created_at, 'snapshot': json.loads(row.snapshot_json)} for row in rows], page, 20, total, request_id(request))

    return router
