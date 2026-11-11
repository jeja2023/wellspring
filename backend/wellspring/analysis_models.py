"""Organization-scoped modeling projects, business models and tactics."""
from datetime import datetime
from sqlalchemy import ForeignKey,Index,Integer,String,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import now,uid
from .types import UTCDateTime


class AnalysisAsset(Base):
    __tablename__='analysis_assets'
    __table_args__=(UniqueConstraint('org_id','kind','code',name='uq_analysis_asset_org_kind_code'),
        Index('ix_analysis_asset_org_kind_created','org_id','kind','created_at','id'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    kind:Mapped[str]=mapped_column(String(20))
    code:Mapped[str]=mapped_column(String(80))
    name:Mapped[str]=mapped_column(String(200))
    category:Mapped[str]=mapped_column(String(30))
    description:Mapped[str]=mapped_column(Text)
    config_json:Mapped[str]=mapped_column(Text)
    project_id:Mapped[str|None]=mapped_column(ForeignKey('analysis_assets.id'),nullable=True)
    model_id:Mapped[str|None]=mapped_column(ForeignKey('analysis_assets.id'),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='DRAFT')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    updated_by:Mapped[str]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)
    updated_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)


class AnalysisAssetEvent(Base):
    __tablename__='analysis_asset_events'
    __table_args__=(Index('ix_analysis_asset_event_created','asset_id','created_at','id'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    asset_id:Mapped[str]=mapped_column(ForeignKey('analysis_assets.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    org_id:Mapped[str]=mapped_column(ForeignKey('organizations.id'))
    action:Mapped[str]=mapped_column(String(30))
    note:Mapped[str]=mapped_column(Text)
    snapshot_json:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=now)
