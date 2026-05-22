from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Iterator, Optional, Union
import duckdb
import pandas as pd

# =========================================================
# MESSAGE COLLECTION
# =========================================================
class MessageCollection:
    """
    DuckDB-backed message store.

    Every public method ultimately calls ``execute()`` which runs
    validated SQL against a DuckDB in-memory database.

    Bracket access
    --------------
    collection[id]          -> _MessageProxy  (read / field access)
    collection[id][key]     -> single field value
    collection[id] += dto   -> insert message
    del collection[id]      -> delete message
    """

    _TABLE = "messages"
    _SCHEMA = """
        id                 INTEGER PRIMARY KEY
        message_id         INTEGER NOT NULL,
        channel_id         INTEGER NOT NULL,
        guild_id           INTEGER,
        author_id          INTEGER NOT NULL,
        content            VARCHAR NOT NULL,
        created_at         VARCHAR NOT NULL,
        edited_at          VARCHAR,
        reply_to_message_id INTEGER,
        attachment_urls    VARCHAR
    """

    def __init__(self) -> None:
        self._conn = duckdb.connect(database=":memory:")
        self._bootstrap()

    def _bootstrap(self) -> None:
        self.execute(f"CREATE TABLE IF NOT EXISTS {self._TABLE} ({self._SCHEMA})")

    # =========================================================
    # CORE: execute
    # =========================================================
    def execute(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        """
        Validate then execute *sql*.  Returns a DataFrame for queries
        that produce results; an empty DataFrame otherwise.
        """
        SQLValidator.validate(sql)

        try:
            if params:
                result = self._conn.execute(sql, params)
            else:
                result = self._conn.execute(sql)

            # DML without result set (INSERT / UPDATE / DELETE)
            if result.description is None:
                return pd.DataFrame()

            return result.fetchdf()

        except duckdb.Error as exc:
            Panic(
                RuntimeError,
                f"DuckDB execution error: {exc}",
                solutions=[
                    "Check your SQL syntax",
                    "Make sure referenced columns/tables exist",
                ],
                note="MessageCollection.execute() failed",
            )
            # Panic always raises, but satisfy the type-checker:
            return pd.DataFrame()  # pragma: no cover

    # =========================================================
    # CRUD
    # =========================================================
    def create(self, dto: MessageDTO) -> pd.DataFrame:
        """INSERT a MessageDTO into the collection."""
        if not isinstance(dto, MessageDTO):
            Panic(
                TypeError,
                f"Expected MessageDTO, got {type(dto).__name__}",
                solutions=["Pass a MessageDTO instance to create()"],
                note="MessageCollection.create type check failed",
            )

        d = dto.to_dict()
        columns = ", ".join(d.keys())
        placeholders = ", ".join(["?"] * len(d))
        sql = f"INSERT INTO {self._TABLE} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, list(d.values()))

    def read(
        self,
        *,
        message_id: int | None = None,
        channel_id: int | None = None,
        author_id: int | None = None,
        guild_id: int | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """SELECT messages with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if message_id is not None:
            clauses.append("message_id = ?")
            params.append(message_id)
        if channel_id is not None:
            clauses.append("channel_id = ?")
            params.append(channel_id)
        if author_id is not None:
            clauses.append("author_id = ?")
            params.append(author_id)
        if guild_id is not None:
            clauses.append("guild_id = ?")
            params.append(guild_id)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM {self._TABLE}{where} ORDER BY created_at"

        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        return self.execute(sql, params if params else None)

    def update(
        self,
        message_id: int,
        *,
        content: str | None = None,
        edited_at: datetime | None = None,
        attachment_urls: list[str] | None = None,
    ) -> pd.DataFrame:
        """UPDATE specific columns of a message."""
        sets: list[str] = []
        params: list[Any] = []

        if content is not None:
            sets.append("content = ?")
            params.append(content)

        if edited_at is not None:
            sets.append("edited_at = ?")
            params.append(edited_at.isoformat())

        if attachment_urls is not None:
            sets.append("attachment_urls = ?")
            params.append(",".join(attachment_urls))

        if not sets:
            Panic(
                ValueError,
                "No fields provided to update",
                solutions=["Pass at least one keyword argument: content, edited_at, attachment_urls"],
                note="MessageCollection.update called with nothing to update",
            )

        set_clause = ", ".join(sets)
        params.append(message_id)
        sql = f"UPDATE {self._TABLE} SET {set_clause} WHERE message_id = ?"
        return self.execute(sql, params)

    def delete(self, message_id: int) -> pd.DataFrame:
        """DELETE a message by its id."""
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            Panic(
                TypeError,
                f"message_id must be int, got {type(message_id).__name__}",
                solutions=["Pass an integer message_id"],
                note="MessageCollection.delete type check failed",
            )
        sql = f"DELETE FROM {self._TABLE} WHERE message_id = ?"
        return self.execute(sql, [message_id])

    # =========================================================
    # BRACKET ACCESS / OPERATOR OVERLOADS
    # =========================================================
    def __getitem__(self, message_id: int) -> _MessageProxy:
        """
        collection[id]  -> returns a _MessageProxy

        Usage:
            collection[1]                # proxy object (shows row repr)
            collection[1]["content"]     # single field
            collection[1] += dto         # insert via proxy
        """
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            Panic(
                TypeError,
                f"Index must be int, got {type(message_id).__name__}",
                solutions=["Use collection[42] with an integer id"],
                note="MessageCollection.__getitem__ type check failed",
            )
        return _MessageProxy(self, message_id)

    def __delitem__(self, message_id: int) -> None:
        """
        del collection[id]  ->  deletes the message
        """
        self.delete(message_id)

    def __len__(self) -> int:
        df = self.execute(f"SELECT COUNT(*) AS cnt FROM {self._TABLE}")
        return int(df.iloc[0]["cnt"])

    def __contains__(self, message_id: int) -> bool:
        df = self.execute(
            f"SELECT 1 FROM {self._TABLE} WHERE message_id = ?", [message_id]
        )
        return not df.empty

    def __iter__(self) -> Iterator[dict[str, Any]]:
        df = self.read()
        for _, row in df.iterrows():
            yield row.to_dict()

    def __repr__(self) -> str:
        return f"<MessageCollection rows={len(self)}>"

# =========================================================
# SQL VALIDATOR
# =========================================================
class SQLValidator:
    """
    Pre-flight SQL validator.
    Catches obvious *issues* *before* they reach the engine.
    """

    # Allowed statement prefixes
    # low cortisol syntax B)
    _ALLOWED_PREFIXES = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "WITH")

    # Dangerous patterns (very basic protection)
    # high cortisol syntax ;-;
    # Those syntax could lead the data to become possibly deleted out of existence
    # It might be tempting to use those syntax, but sorry no pass.
    _DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r";\s*DROP\s+", re.IGNORECASE),
        re.compile(r";\s*DELETE\s+", re.IGNORECASE),
        re.compile(r"--"),
    ]

    @classmethod
    def validate(cls, sql: str) -> None:
        if not isinstance(sql, str):
            Panic(
                TypeError,
                f"SQL command must be a string, got {type(sql).__name__}",
                solutions=["Pass a valid SQL string to execute()"],
                note="SQLValidator type check failed",
            )

        stripped = sql.strip()
        if not stripped:
            Panic(
                ValueError,
                "SQL command is empty",
                solutions=["Provide a non-empty SQL string"],
                note="SQLValidator empty check failed",
            )

        # Check statement prefix
        first_word = stripped.split()[0].upper()
        if first_word not in cls._ALLOWED_PREFIXES:
            Panic(
                SyntaxError,
                f"Unrecognised SQL statement start: '{first_word}'",
                solutions=[
                    f"Allowed prefixes: {', '.join(cls._ALLOWED_PREFIXES)}",
                    "Check for typos in your SQL command",
                ],
                note="SQLValidator prefix check failed",
            )

        # Balanced parentheses
        if stripped.count("(") != stripped.count(")"):
            Panic(
                SyntaxError,
                "Unbalanced parentheses in SQL command",
                solutions=["Check opening/closing parentheses"],
                note="SQLValidator parentheses check failed",
            )

        # Dangerous patterns
        for pattern in cls._DANGEROUS_PATTERNS:
            if pattern.search(stripped):
                Panic(
                    SyntaxError,
                    f"Potentially dangerous SQL pattern detected: {pattern.pattern}",
                    solutions=["Remove injection-style patterns"],
                    note="SQLValidator injection check failed",
                )



# =========================================================
# MESSAGE PROXY  (enables  collection[id][key]  syntax)
# =========================================================
class _MessageProxy:
    """
    A thin proxy returned by  ``MessageCollection[id]``.

    Supports:
        proxy[key]      -> get a single field value
        proxy += dto     -> insert a new message at this id
        del proxy        -> delete the message from the collection
    """
    # TODO: For dev, can you suggest another way to simplify it? Or maybe add another feature?

    def __init__(self, collection: MessageCollection, message_id: int) -> None:
        self._collection = collection
        self._message_id = message_id

    # ---------- collection[id][key] ----------
    def __getitem__(self, key: str) -> Any:
        df = self._collection.read(message_id=self._message_id)
        if df.empty:
            Panic(
                KeyError,
                f"No message found with message_id={self._message_id}",
                solutions=["Check the message_id exists in the collection"],
                note="_MessageProxy __getitem__ failed",
            )
        valid_columns = list(df.columns)
        if key not in valid_columns:
            Panic(
                KeyError,
                f"Unknown field '{key}'",
                solutions=[f"Valid fields: {valid_columns}"],
                note="_MessageProxy field lookup failed",
            )
        return df.iloc[0][key]

    # ---------- collection[id] += MessageDTO ----------
    def __iadd__(self, dto: MessageDTO) -> _MessageProxy:
        if not isinstance(dto, MessageDTO):
            Panic(
                TypeError,
                f"Can only += a MessageDTO, got {type(dto).__name__}",
                solutions=["Use:  collection[id] += MessageDTO(...)"],
                note="_MessageProxy iadd type check failed",
            )
        self._collection.create(dto)
        return self

    # ---------- pretty print ----------
    def __repr__(self) -> str:
        df = self._collection.read(message_id=self._message_id)
        if df.empty:
            return f"<_MessageProxy message_id={self._message_id} NOT_FOUND>"
        row = df.iloc[0].to_dict()
        return f"<_MessageProxy message_id={self._message_id} {row}>"
