# Contributor Note

We separate models/ and services/ so that there exist two folders: message (related), and processor (related).

## Message

This is one of the instance responsible for Discord Message in the future. There exist two objects under Message, they are: message (MessageDTO) and message_collection (MessageCollection).

### MessageDTO

Immutable data-transfer object (`@dataclass(frozen=True, slots=True)`).

#### Attributes

| Attribute             | Type                 | Description                                           |
| --------------------- | -------------------- | ----------------------------------------------------- |
| `ID`                  | `Optional[int]`      | Database primary key. `None` means DB auto-increment. |
| `message_id`          | `int`                | Discord message ID.                                   |
| `channel_id`          | `int`                | Discord channel ID.                                   |
| `guild_id`            | `Optional[int]`      | Discord server ID. `None` if DM.                      |
| `author_id`           | `int`                | Discord user ID of sender.                            |
| `content`             | `str`                | Raw message content.                                  |
| `created_at`          | `datetime`           | Timestamp when message was created.                   |
| `edited_at`           | `Optional[datetime]` | Timestamp when message was edited.                    |
| `reply_to_message_id` | `Optional[int]`      | Target message ID if this is a reply.                 |
| `attachment_urls`     | `list[str]`          | List of attachment URLs.                              |

---

#### Properties

| Property          | Return Type      | Description                                                       |
| ----------------- | ---------------- | ----------------------------------------------------------------- |
| `name`            | `str`            | Resolves readable username from `author_id`. Placeholder for now. |
| `is_edited`       | `bool`           | `True` if `edited_at` exists.                                     |
| `has_attachments` | `bool`           | `True` if attachment list is not empty.                           |
| `to_dict`         | `dict[str, Any]` | Converts object into flat dictionary for DB/storage usage.        |

---

#### Public Methods

| Method            | Description                                                              |
| ----------------- | ------------------------------------------------------------------------ |
| `__post_init__()` | Runs automatic validation after object creation. Prevents invalid state. |

---

#### Private Helper Methods

| Method                                               | Description                                  |
| ---------------------------------------------------- | -------------------------------------------- |
| `_resolve_author_name()`                             | Maps `author_id` into readable username.     |
| `_validate_positive_int(field_name, value)`          | Ensures value is positive integer.           |
| `_validate_optional_positive_int(field_name, value)` | Same as above, but allows `None`.            |
| `_validate_string(field_name, value)`                | Ensures value is `str`.                      |
| `_validate_datetime(field_name, value)`              | Ensures value is `datetime`.                 |
| `_validate_optional_datetime(field_name, value)`     | Same as above, but allows `None`.            |
| `_validate_attachment_urls(value)`                   | Ensures attachment list contains valid URLs. |
| `_validate_business_rules()`                         | Validates logical rules between fields.      |

---

#### Validation Rules

| Rule                                                    | Reason                               |
| ------------------------------------------------------- | ------------------------------------ |
| IDs must be positive integers                           | Prevent invalid Discord/database IDs |
| `content` must be string                                | Prevent malformed payload            |
| `created_at` must exist                                 | Message must have creation timestamp |
| `edited_at >= created_at`                               | Prevent impossible timestamps        |
| Message cannot reply to itself                          | Prevent recursive relationship       |
| Attachment URLs must start with `http://` or `https://` | Basic URL validation                 |

---

#### Design Characteristics

| Feature         | Purpose                                |
| --------------- | -------------------------------------- |
| `frozen=True`   | Makes object immutable after creation  |
| `slots=True`    | Reduces memory usage                   |
| DTO Pattern     | Separates raw data from business logic |
| Self-validation | Prevents invalid object states early   |

---

### MessageCollection

DuckDB-backed repository for storing and querying `MessageDTO`.

Acts as:

- Repository Layer
- CRUD Service
- In-memory database wrapper
- Collection-like object

---

#### Core Attributes

| Attribute | Type                | Description                             |
| --------- | ------------------- | --------------------------------------- |
| `_TABLE`  | `str`               | Database table name (`messages`)        |
| `_SCHEMA` | `str`               | SQL schema definition for message table |
| `_conn`   | `duckdb.Connection` | Active in-memory DuckDB connection      |

---

#### Constructor

| Method       | Description                                              |
| ------------ | -------------------------------------------------------- |
| `__init__()` | Initializes DuckDB memory database and bootstraps schema |

---

#### Internal Methods

| Method         | Description                                     |
| -------------- | ----------------------------------------------- |
| `_bootstrap()` | Creates sequence + messages table if not exists |

---

#### Public Properties

| Property       | Return Type    | Description                                   |
| -------------- | -------------- | --------------------------------------------- |
| `to_dataframe` | `pd.DataFrame` | Returns entire collection as pandas DataFrame |

---

#### Core Execution Layer

#### `execute(sql, params=None)`

| Parameter | Type                | Description               |
| --------- | ------------------- | ------------------------- |
| `sql`     | `str`               | SQL query                 |
| `params`  | `list[Any] \| None` | Prepared statement values |

#### Returns

`pd.DataFrame`

#### Responsibilities

- Validates SQL using `SQLValidator`
- Executes SQL safely
- Handles prepared parameters
- Converts result into pandas DataFrame
- Raises `Panic()` on database errors

---

#### CRUD Operations

#### `create(dto)`

| Parameter | Type         |
| --------- | ------------ |
| `dto`     | `MessageDTO` |

#### Description

Inserts new message into database.

#### Internal Flow

```text
MessageDTO
   ↓
to_dict
   ↓
INSERT INTO messages
```

---

#### `read(...)`

#### Optional Filters

| Filter       | Type          |
| ------------ | ------------- |
| `ID`         | `int \| None` |
| `message_id` | `int \| None` |
| `channel_id` | `int \| None` |
| `author_id`  | `int \| None` |
| `guild_id`   | `int \| None` |
| `limit`      | `int \| None` |

#### Description

Dynamically builds SQL `WHERE` clause based on provided filters.

#### Returns

`pd.DataFrame`

---

#### `update(ID, ...)`

#### Editable Fields

| Field             | Type                |
| ----------------- | ------------------- |
| `content`         | `str \| None`       |
| `edited_at`       | `datetime \| None`  |
| `attachment_urls` | `list[str] \| None` |

#### Description

Updates existing message row by primary key.

#### Validation

Fails if no fields are provided.

---

#### `delete(ID)`

| Parameter | Type  |
| --------- | ----- |
| `ID`      | `int` |

#### Description

Deletes message row by primary key.

---

#### Operator Overloads

These make the collection behave like a Python container.

---

#### `__getitem__(ID)`

#### Syntax

```python
collection[1]
```

#### Returns

`_MessageProxy`

#### Purpose

Enables:

```python
collection[1]["content"]
```

---

#### `__setitem__(row_id, proxy)`

#### Purpose

Required because Python rewrites:

```python
collection[1] += dto
```

Into:

```python
collection.__setitem__(
    1,
    collection.__getitem__(1).__iadd__(dto)
)
```

####

Acts as no-op receiver.

---

#### `__delitem__(ID)`

#### Syntax

```python
del collection[1]
```

#### Purpose

Deletes row.

---

#### `__len__()`

#### Returns

`int`

#### Description

Returns total message count.

---

#### `__contains__(ID)`

#### Syntax

```python
1 in collection
```

#### Returns

`bool`

#### Description

Checks whether row exists.

---

#### `__iter__()`

#### Returns

`Iterator[dict[str, Any]]`

#### Description

Allows iteration:

```python
for row in collection:
    print(row)
```

---

#### `__repr__()`

#### Description

Pretty-print collection summary.

Example:

```python
<MessageCollection rows=15>
```

---

#### `SQLValidator`

Static SQL pre-flight validator.

Purpose:

- Prevent malformed SQL
- Block obvious injection patterns
  -####Enforce controlled SQL usage

---

#### Class Attributes

| Attribute             | Type            | Description                      |
| --------------------- | --------------- | -------------------------------- |
| `_ALLOWED_PREFIXES`   | `tuple[str]`    | Allowed SQL statement types      |
| `_DANGEROUS_PATTERNS` | `list[Pattern]` | Regex patterns for dangerous SQL |

---

#### `validate(sql)`

| Parameter | Type  |
| --------- | ----- |
| `sql`     | `str` |

#### Validation Rules

| Rule                       | Reason                      |
| -------------------------- | --------------------------- |
| SQL must be string         | Prevent invalid execution   |
| SQL cannot be empty        | Prevent meaningless queries |
| Prefix must be allowed     | Restrict query types        |
| Parentheses must balance   | Basic syntax sanity check   |
| Dangerous patterns blocked | Basic injection defense     |

#### Dangerous Patterns

```sql
; DROP
; DELETE
--
```

---

#### `_MessageProxy`

Thin proxy object returned by:

```python
collection[ID]
```

Provides:

- field lookup
- insertion syntax
- pretty representation

---

#### Attributes

| Attribute     | Type                | Description       |
| ------------- | ------------------- | ----------------- |
| `_collection` | `MessageCollection` | Parent collection |
| `_ID`         | `int`               | Target row ID     |

---

#### Constructor

| Method                     | Description                  |
| -------------------------- | ---------------------------- |
| `__init__(collection, ID)` | Creates proxy for target row |

---

#### `__getitem__(key)`

#### Syntax

```python
collection[1]["content"]
```

#### Returns

Single field value.

#### Validation

- Row must exist
- Column name must exist

---

#### `__iadd__(dto)`

#### Syntax

```python
collection[2] += dto
```

#### Purpose

Inserts `MessageDTO`.

#### Returns

`_MessageProxy`

---

#### `__repr__()`

#### Example

```python
<_MessageProxy ID=1 {'content': 'hello'}>
```

If missing:

```python
<_MessageProxy ID=1 NOT_FOUND>
```

---

#### Architectural Relationships

```text
+-------------------+
|   MessageDTO      |
+-------------------+
| Immutable DTO     |
| Self-validating   |
+---------+---------+
          |
          | inserted/read
          v
+-------------------+
| MessageCollection |
+-------------------+
| CRUD Layer        |
| DuckDB Wrapper    |
| Python Container  |
+---------+---------+
          |
          | validates SQL
          v
+-------------------+
|   SQLValidator    |
+-------------------+
| SQL safety checks |
+-------------------+

collection[ID]
        ↓
+-------------------+
|   _MessageProxy   |
+-------------------+
| Field access      |
| += insertion      |
| Pretty access     |
+-------------------+
```

---

#### Design Patterns Used

| Pattern              | Usage                            |
| -------------------- | -------------------------------- |
| DTO                  | `MessageDTO`                     |
| Repository           | `MessageCollection`              |
| Proxy                | `_MessageProxy`                  |
| Active Validation    | `SQLValidator`                   |
| Operator Overloading | `[]`, `+=`, `del`, `in`, `len()` |

---

#### Notable Design Decisions

| Decision                  | Reason                      |
| ------------------------- | --------------------------- |
| DuckDB in-memory          | Fast temporary analytics    |
| Pandas integration        | Easy export and analysis    |
| SQL abstraction           | Flexible querying           |
| Proxy layer               | Cleaner bracket syntax      |
| Immutable DTO             | Prevent accidental mutation |
| Prepared statements (`?`) | Reduce SQL injection risk   |

---

#### Future Plank

| Future Plan                         | Benefit                    |
| ----------------------------------- | -------------------------- |
| Store timestamps as TIMESTAMP       | Better sorting/filtering   |
| Add `fetch_one()`                   | Avoid DataFrame overhead   |
| Replace regex validator with parser | Safer SQL validation       |
| Add async support                   | Better Discord integration |
| Add caching layer                   | Faster repeated lookups    |
| Add schema migration system         | Easier evolution           |
| Add typed query builder             | Stronger safety            |
| Replace proxy insertion syntax      | Clearer semantics          |

#### `MessageCollection`

Container/service layer for managing `MessageDTO`.

```

```

```

## Processor (ru Part)
coming soon...
```

## ArgsScraper (coming soon)

## Config (coming soon)

## DiscordScraper (coming soon)
