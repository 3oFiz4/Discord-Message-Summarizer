from __future__ import annotations

import copy
import importlib.util
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence
from .error_logger import Panic

# Note that.. Due to my laziness and wanted to focus on the other object, I let gpt-oss-120b to provide a better comment for each function. I have not review them, but let me know if something is not right.

# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

# PURPOSE:
# Merge two dictionaries recursively.
#
# HOW IT WORKS:
# - `base` becomes the foundation.
# - `override` replaces or extends values inside `base`.
# - Nested dictionaries are merged recursively.
# - Non-dict values are fully replaced.
#
# WHY deepcopy?
# To avoid mutating the original input dictionaries.
#
# EXAMPLE:
# base = {"db": {"host": "localhost", "port": 3306}}
# override = {"db": {"port": 5432}}
#
# result:
# {"db": {"host": "localhost", "port": 5432}}
#
# USAGE:
# Used when multiple config sources are loaded and merged together.
def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

# PURPOSE:
# Convert every dictionary key into lowercase recursively.
#
# WHY?
# So config access becomes case-insensitive.
#
# EXAMPLE:
# {"DATABASE": {"HOST": "localhost"}}
#
# becomes:
# {"database": {"host": "localhost"}}
#
# USAGE:
# Called before configs are merged together.
def _normalize_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k).lower(): _normalize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_keys(v) for v in value]
    return value

# PURPOSE:
# Convert string values from `.env` files into proper Python types.
#
# EXAMPLE:
# "true"  -> True
# "123"   -> 123
# "3.14"  -> 3.14
# "null"  -> None
# "[1,2]" -> [1,2]
#
# WHY?
# Environment files only contain strings.
# This parser restores real data types.
#
# USAGE:
# Used by EnvConfigSource.
def _parse_env_value(value: str) -> Any:
    value = value.strip()

    # Remove surrounding quotes.
    #
    # EXAMPLE:
    # "hello" -> hello
    # 'hello' -> hello
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        value = value[1:-1]

    lowered = value.lower()

    # Convert boolean strings.
    if lowered == "true":
        return True

    if lowered == "false":
        return False

    # Convert null-like strings.
    if lowered in {"none", "null"}:
        return None

    # Try integer conversion.
    try:
        return int(value)
    except ValueError:
        pass

    # Try float conversion.
    try:
        return float(value)
    except ValueError:
        pass

    # Try JSON conversion.
    #
    # EXAMPLE:
    # {"a":1}
    # [1,2,3]
    if value.startswith("{") or value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # Fallback to raw string.
    return value

# PURPOSE:
# Insert nested keys into a dictionary using separators.
#
# EXAMPLE:
# key = "database__host"
#
# becomes:
# {
#     "database": {
#         "host": value
#     }
# }
#
# WHY?
# Environment variables cannot naturally represent nested objects.
#
# USAGE:
# Used by EnvConfigSource.
def _insert_nested(
    target: dict[str, Any],
    key: str,
    value: Any,
    separator: str = "__",
) -> None:
    # Split nested keys.
    parts = key.split(separator)

    current = target

    # Create intermediate dictionaries.
    for part in parts[:-1]:

        if part not in current or not isinstance(current[part], dict):
            current[part] = {}

        current = current[part]

    # Insert final value.
    current[parts[-1]] = value

# ──────────────────────────────────────────────
#  Config Sources
# ──────────────────────────────────────────────

# ABSTRACT BASE CLASS
#
# PURPOSE:
# Every config source inherits from this.
#
# Supported examples:
# - JSON files
# - Python files
# - ENV files
#
# This class defines:
# - common path handling
# - file existence checks
# - abstract load() method
class ConfigSource(ABC):
    def __init__(self, path: str | Path, required: bool = True):
        self.path = Path(path)
        self.required = required

    def _ensure_file(self) -> bool:
        if self.path.exists():
            return True
        if self.required:
            Panic(
                FileNotFoundError,
                f"Config file not found: {self.path}",
                solutions=[
                    f"Create the file at {self.path.resolve()}",
                    "Pass required=False to make this source optional",
                ],
            )
        return False

    @abstractmethod
    def load(self) -> dict[str, Any]:
        raise NotImplementedError

# PURPOSE:
# Load configuration from JSON files.
#
# EXAMPLE FILE:
# {
#     "database": {
#         "host": "localhost"
#     }
# }
class JsonConfigSource(ConfigSource):
    def load(self) -> dict[str, Any]:
        # MAIN LOADER
        #
        # PROCESS:
        # 1. Ensure file exists
        # 2. Parse JSON
        # 3. Validate top-level object
        # 4. Return dictionarydef load(self) -> dict[str, Any]:
        if not self._ensure_file():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            Panic(
                json.JSONDecodeError,
                f"Invalid JSON in {self.path}: {exc.msg}",
                solutions=[
                    "Validate the file at https://jsonlint.com",
                    f"Check line {exc.lineno}, column {exc.colno}",
                ],
            )

        if not isinstance(data, dict):
            Panic(
                ValueError,
                f"JSON config must contain an object at the top level: {self.path}",
                solutions=[
                    "Wrap your JSON content in { }",
                ],
            )

        return data

# PURPOSE:
# Load configuration from Python files.
#
# SUPPORTED:
#
# CONFIG = {
#     "debug": True
# }
#
# OR:
#
# DEBUG = True
# PORT = 8080
#
# WHY USE PYTHON CONFIG?
# - dynamic logic
# - computed values
# - easier advanced configuration
class PythonConfigSource(ConfigSource):
    def load(self) -> dict[str, Any]:
        if not self._ensure_file():
            return {}

        spec = importlib.util.spec_from_file_location(
            f"_config_{self.path.stem}_{id(self)}",
            self.path,
        )
        if spec is None or spec.loader is None:
            Panic(
                ImportError,
                f"Unable to import Python config: {self.path}",
                solutions=[
                    "Check that the file is valid Python",
                    "Make sure the file is not empty",
                ],
            )

        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            Panic(
                type(exc),
                f"Error executing Python config {self.path}: {exc}",
                solutions=[
                    "Check the file for syntax or runtime errors",
                    "Try running the file standalone with python",
                ],
            )

        data: dict[str, Any] = {}

        if hasattr(module, "CONFIG"):
            if not isinstance(module.CONFIG, dict):
                Panic(
                    TypeError,
                    f"'CONFIG' must be a dict in {self.path}, got {type(module.CONFIG).__name__}",
                    solutions=[
                        'Define CONFIG as a dictionary: CONFIG = { "key": "value" }',
                    ],
                )
            data = _deep_merge(data, module.CONFIG)

        uppercase_vars = {
            name: value
            for name, value in vars(module).items()
            if name.isupper() and not name.startswith("_")
        }

        data = _deep_merge(data, uppercase_vars)
        return data

# PURPOSE:
# Load `.env`-style configuration files.
#
# EXAMPLE:
#
# DEBUG=true
# DATABASE__HOST=localhost
# DATABASE__PORT=3306
#
# OUTPUT:
#
# {
#     "debug": True,
#     "database": {
#         "host": "localhost",
#         "port": 3306
#     }
# }
class EnvConfigSource(ConfigSource):
    def __init__(
        self,
        path: str | Path,
        required: bool = True,
        separator: str = "__",
    ):
        super().__init__(path, required=required)
        self.separator = separator
    # MAIN LOADER
    #
    # PROCESS:
    # 1. Read line-by-line
    # 2. Ignore comments
    # 3. Parse KEY=VALUE
    # 4. Convert types
    # 5. Insert nested keys
    def load(self) -> dict[str, Any]:
        if not self._ensure_file():
            return {}

        data: dict[str, Any] = {}

        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[7:].strip()

            key, sep, value = line.partition("=")
            if not sep:
                continue

            key = key.strip().lower()
            value = _parse_env_value(value.strip())
            _insert_nested(data, key, value, self.separator)

        return data


# ──────────────────────────────────────────────
#  Config Object
# ──────────────────────────────────────────────

# PURPOSE:
# Wrapper object around config dictionaries.
#
# FEATURES:
# - dot access
# - bracket access
# - recursive nested sections
#
# EXAMPLE:
#
# config.database.host
# config["database"]["host"]
class ConfigSection:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in {
            "to_dict", "get", "keys", "items", "values",
        }:
            raise AttributeError(name)

        key = name.lower()
        if key not in self._data:
            Panic(
                AttributeError,
                f"No config key named '{name}'",
                solutions=[
                    f"Available keys: {', '.join(self._data.keys())}",
                    f"Check your config files for typos",
                ],
            )

        value = self._data[key]
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def __getitem__(self, key: str) -> Any:
        key = key.lower()
        if key not in self._data:
            Panic(
                KeyError,
                f"No config key named '{key}'",
                solutions=[
                    f"Available keys: {', '.join(self._data.keys())}",
                ],
            )

        value = self._data[key]
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        value = self._data.get(key.lower(), default)
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._data})"

# MAIN CONFIG OBJECT
#
# PURPOSE:
# Combine multiple config sources into one object.
#
# EXAMPLE:
#
# config = Config(
#     JsonConfigSource("config.json"),
#     EnvConfigSource(".env")
# ).load()
#
# ACCESS:
# config.database.host
class Config(ConfigSection):
    def __init__(self, *sources: ConfigSource, normalize_keys: bool = True):
        self.sources = list(sources)
        self.normalize_keys = normalize_keys
        super().__init__({})
    # MAIN LOAD PROCESS
    #
    # PROCESS:
    # 1. Load every source
    # 2. Normalize keys
    # 3. Merge all configs
    # 4. Store final data
    #
    # MERGE ORDER:
    # Later sources override earlier sources.
    #
    # EXAMPLE:
    #
    # Config(
    #     JsonConfigSource("base.json"),
    #     EnvConfigSource(".env")
    # )
    #
    # `.env` values override `base.json`.
    def load(self) -> "Config":
        merged: dict[str, Any] = {}

        for source in self.sources:
            data = source.load()
            if self.normalize_keys:
                data = _normalize_keys(data)
            merged = _deep_merge(merged, data)

        if not merged:
            Panic(
                ValueError,
                "All config sources produced empty data",
                solutions=[
                    "Check that at least one config file exists and is not empty",
                    "Verify file paths passed to each source",
                ],
                note="The app cannot start without any configuration",
            )

        self._data = merged
        return self

    def reload(self) -> "Config":
        return self.load()

    def require(self, dotted_key: str) -> Any:
        current: Any = self._data

        for part in dotted_key.lower().split("."):
            if not isinstance(current, dict) or part not in current:
                Panic(
                    KeyError,
                    f"Missing required config key: '{dotted_key}'",
                    solutions=[
                        f"Add '{dotted_key}' to one of your config files",
                        f"Check for typos — available top-level keys: {', '.join(self._data.keys())}",
                    ],
                )
            current = current[part]

        if isinstance(current, dict):
            return ConfigSection(current)
        return current
