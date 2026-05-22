from services.helper.config_manager import Config, JsonConfigSource, PythonConfigSource, EnvConfigSource

# ── Config sources ──────────────────────
# Earlier = lower priority, later = overrides

_sources = [
    PythonConfigSource("scraper_config.py",  required=True),
    EnvConfigSource(".env",            required=True),
]

config = Config(*_sources).load()
