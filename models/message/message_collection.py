from __future__ import annotations
from .message import MessageDTO
from services.helper.error_logger import Panic

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
    collection[ID]          -> _MessageProxy  (read / field access)
    collection[ID][key]     -> single field value
    collection[ID] += dto   -> insert message
    del collection[ID]      -> delete message
    """

    _TABLE = "messages"
    _SCHEMA = """
        ID                  INTEGER PRIMARY KEY DEFAULT nextval('messages_id_seq'),
        message_id          INTEGER NOT NULL,
        channel_id          INTEGER NOT NULL,
        guild_id            INTEGER,
        author_id           INTEGER NOT NULL,
        content             VARCHAR NOT NULL,
        created_at          VARCHAR NOT NULL,
        edited_at           VARCHAR,
        reply_to_message_id INTEGER,
        attachment_urls     VARCHAR
    """

    def __init__(self) -> None:
        self._conn = duckdb.connect(database=":memory:")
        self._bootstrap()

    def _bootstrap(self) -> None:
        self.execute("CREATE SEQUENCE IF NOT EXISTS messages_id_seq START 1")
        self.execute(f"CREATE TABLE IF NOT EXISTS {self._TABLE} ({self._SCHEMA})")

    # Yeah it's a property lol...
    @property
    def to_dataframe(self) -> pd.DataFrame:
        """Return entire collection as a pandas DataFrame."""
        df = self.read()
        return df if df is not None else pd.DataFrame()

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

        d = dto.to_dict
        columns = ", ".join(d.keys())
        placeholders = ", ".join(["?"] * len(d))
        sql = f"INSERT INTO {self._TABLE} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, list(d.values()))

    def read(
    self,
    *,
    ID: int | None = None,
    message_id: int | None = None,
    channel_id: int | None = None,
    author_id: int | None = None,
    guild_id: int | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
        clauses: list[str] = []
        params: list[Any] = []

        if ID is not None:
            clauses.append("ID = ?")
            params.append(ID)
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
    ID: int,  # <-- primary key
    *,
    content: str | None = None,
    edited_at: datetime | None = None,
    attachment_urls: list[str] | None = None,
) -> pd.DataFrame:
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
            Panic(ValueError, "No fields provided to update",
                solutions=["Pass at least one keyword argument"],
                note="MessageCollection.update called with nothing to update")

        set_clause = ", ".join(sets)
        params.append(ID)
        sql = f"UPDATE {self._TABLE} SET {set_clause} WHERE ID = ?"
        return self.execute(sql, params)

    def delete(self, ID: int) -> pd.DataFrame:
        if not isinstance(ID, int) or isinstance(ID, bool):
            Panic(TypeError, f"ID must be int, got {type(ID).__name__}",
                solutions=["Pass an integer ID"],
                note="MessageCollection.delete type check failed")
        sql = f"DELETE FROM {self._TABLE} WHERE ID = ?"
        return self.execute(sql, [ID])

    # =========================================================
    # BRACKET ACCESS / OPERATOR OVERLOADS
    # =========================================================
    def __getitem__(self, ID: int) -> _MessageProxy:
        """
        collection[ID]  -> returns a _MessageProxy

        Usage:
            collection[1]                # proxy object (shows row repr)
            collection[1]["content"]     # single field
            collection[1] += dto         # insert via proxy
        """
        if not isinstance(ID, int) or isinstance(ID, bool):
            Panic(TypeError, f"Index must be int, got {type(ID).__name__}",
                solutions=["Use collection[42] with an integer ID"],
                note="MessageCollection.__getitem__ type check failed")
            return None # Panic printed; return None <GuardRail>
        return _MessageProxy(self, ID)
    
    def __setitem__(self, row_id: int, proxy: _MessageProxy) -> None:
        """
        Required for  collection[id] += dto  to work.
        Python's  a[x] += y  desugars to  a[x] = a[x].__iadd__(y)
        so __setitem__ must exist to receive the result.
        """
        # The actual insertion already happened inside __iadd__.
        # This is a no-op receiver so Python doesn't raise TypeError.
        pass

    def __delitem__(self, ID: int) -> None:
        """
        del collection[ID]  ->  deletes the message
        """
        self.delete(ID)

    def __len__(self) -> int:
        df = self.execute(f"SELECT COUNT(*) AS cnt FROM {self._TABLE}")
        return int(df.iloc[0]["cnt"])

    def __contains__(self, ID: int) -> bool:
        df = self.execute(
            f"SELECT 1 FROM {self._TABLE} WHERE ID = ?", [ID]
        )
        return not df.empty

    def __iter__(self) -> Iterator[dict[str, Any]]:
        df = self.read()
        for _, row in df.iterrows():
            yield row.to_dict

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

    def __init__(self, collection: MessageCollection, ID: int) -> None:
            self._collection = collection
            self._ID = ID

    # ---------- collection[ID][key] ----------
    def __getitem__(self, key: str) -> Any:
            df = self._collection.read(ID=self._ID)
            if df.empty:
                Panic(KeyError, f"No message found with ID={self._ID}",
                    solutions=["Check the ID exists in the collection"],
                    note="_MessageProxy __getitem__ failed")
            valid_columns = list(df.columns)
            if key not in valid_columns:
                Panic(KeyError, f"Unknown field '{key}'",
                    solutions=[f"Valid fields: {valid_columns}"],
                    note="_MessageProxy field lookup failed")
            return df.iloc[0][key]

    # ---------- collection[ID] += MessageDTO ----------
    def __iadd__(self, dto: MessageDTO) -> _MessageProxy:
        if not isinstance(dto, MessageDTO):
            Panic(TypeError, f"Can only += a MessageDTO, got {type(dto).__name__}",
                solutions=["Use:  collection[id] += MessageDTO(...)"],
                note="_MessageProxy iadd type check failed")
        self._collection.create(dto)
        return self

    # ---------- pretty print ----------
    def __repr__(self) -> str:
            df = self._collection.read(ID=self._ID)
            if df.empty:
                return f"<_MessageProxy ID={self._ID} NOT_FOUND>"
            row = df.iloc[0].to_dict
            return f"<_MessageProxy ID={self._ID} {row}>"

# <------------------ TEST --------------------->
# collection = MessageCollection()
#
# msg1 = MessageDTO(
#         ID=None,
#         message_id=1,
#         channel_id=10,
#         guild_id=999,
#         author_id=333,
#         content="Hello everyone!",
#         created_at=datetime.strptime("05/08/2006 14:5:20", "%m/%d/%Y %H:%M:%S"),
#         edited_at=None,
#         reply_to_message_id=None,
#         attachment_urls=[],
#     )
# msg2 = MessageDTO(
#         ID=None,
#         message_id=2,
#         channel_id=10,
#         guild_id=999,
#         author_id=1002,
#         content="Hi Alice, welcome!",
#         created_at=datetime(2026, 5, 22, 10, 1, 0),
#         edited_at=datetime(2026, 5, 22, 10, 2, 0),
#         reply_to_message_id=1,
#         attachment_urls=["https://cdn.example.com/welcome.png"],
#     )
#
# msg3 = MessageDTO(
#         ID=None,
#     message_id=3,
#     channel_id=11,
#     guild_id=999,
#     author_id=1003,
#     content="General discussion topic",
#     created_at=datetime(2026, 5, 22, 11, 0, 0),
#     edited_at=None,
#     reply_to_message_id=None,
# )
#
# collection.create(msg1)
# collection.create(msg2)
# collection.create(msg3)
#
# print("=== collection ===")
# print(collection)
# print("OK")
#
# # ---- READ (all) ----
# print("=== read all ===")
# print(collection.read())
# print("OK")
#
# # ---- READ (filtered) ----
# print("=== read channel_id=10 ===")
# print(collection.read(channel_id=10))
# print("OK")
#
# # ---- BRACKET ACCESS  collection[ID] ----
# print("=== collection[1] === ISSSSSSUEEEEE")
# proxy = collection[1]
# print(proxy)
# print("OK")
#
# # ---- BRACKET FIELD ACCESS  collection[ID][key] ----
# print("=== collection[2]['content'] ===")
# print(collection.read(ID=2))
# print(collection[2]["content"])
# print("OK")
#
# print("=== collection[2]['attachment_urls'] ===")
# print(collection[2]["attachment_urls"])
# print("OK")
#
# # ---- BRACKET INSERT  collection[ID] += MessageDTO(...) ----
# print("=== collection[4] += MessageDTO(...) ===")
# msg4 = MessageDTO(
#     ID=5,
#     message_id=4,
#     channel_id=10,
#     guild_id=999,
#     author_id=1001,
#     content="Another message from Alice",
#     created_at=datetime(2026, 5, 22, 12, 0, 0),
#     edited_at=None,
#     reply_to_message_id=None,
# )
# print(collection[1])
# print()
#
# # ---- UPDATE ----
# print("=== update message 1 ===")
# collection.update(1, content="Hello everyone! (edited)", edited_at=datetime(2026, 5, 22, 10, 5, 0))
# print(collection[1])
# print("OK")
#
# # ---- DELETE via bracket ----
# print("=== del collection[3] ===")
# del collection[3]
# print(f"3 in collection: {3 in collection}")
# print("OK")
#
# # ---- ITERATE ----
# print("=== iterate ===")
# for row in collection:
#     print(row)
# print("OK")
#
# # ---- LEN / CONTAINS ----
# print(f"len = {len(collection)}")
# print(f"1 in collection = {1 in collection}")
# print(f"3 in collection = {3 in collection}")
# print(collection)
# print("OK")
# # ---- Incase for DataScience ---- #
# print(collection.execute(f"SELECT ID, content FROM {collection._TABLE}"))
# df = collection.to_dataframe
# print(df)
# df.to_csv("output.csv") # export... cool rite?
#
# print("no error")
