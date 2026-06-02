"""
api/services/__init__.py
────────────────────────
Service layer package. Each module contains pure business logic functions
that accept injected dependencies (AsyncSession, Redis) and return ORM
objects or raise HTTPException. No FastAPI routing lives here.
"""
