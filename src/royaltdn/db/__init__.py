"""Database persistence layer for TimescaleDB.

Provides ``DBRepository`` for async CRUD via ``asyncpg``, ``NullDBRepository``
as a no-op fallback when the database is unreachable, and ``get_repository()``
as a singleton factory.
"""

from __future__ import annotations

from royaltdn.db.repository import DBRepository, NullDBRepository, get_repository, init_pool

__all__ = [
    "DBRepository",
    "NullDBRepository",
    "get_repository",
    "init_pool",
]
