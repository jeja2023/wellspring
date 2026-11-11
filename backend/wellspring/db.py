import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wellspring-dev.db")
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    # Runtime requests should fail in bounded time; schema migrations use their
    # own engine and are deliberately not subject to these request budgets.
    connect_args = {
        "connect_timeout": max(1, int(os.getenv("WELLSPRING_DB_CONNECT_TIMEOUT", "5"))),
        "options": "-c statement_timeout={} -c lock_timeout={}".format(
            max(1, int(os.getenv("WELLSPRING_DB_STATEMENT_TIMEOUT_MS", "15000"))),
            max(1, int(os.getenv("WELLSPRING_DB_LOCK_TIMEOUT_MS", "5000"))),
        ),
    }
engine_options = {"connect_args": connect_args, "pool_pre_ping": True, "hide_parameters": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options["pool_timeout"] = 10
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
