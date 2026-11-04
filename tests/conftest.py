import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@127.0.0.1:5432/test",
)
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("STORAGE_BACKEND", "memory")
