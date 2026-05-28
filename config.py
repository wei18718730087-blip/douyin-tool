import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(f"DOUYIN_{key}", default)


@dataclass
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    output_dir: str = field(
        default_factory=lambda: _env("OUTPUT_DIR", str(Path.home() / "Downloads" / "douyin"))
    )
    default_keyword_count: int = field(
        default_factory=lambda: int(_env("DEFAULT_KEYWORD_COUNT", "20"))
    )
    default_keyword_method: str = field(
        default_factory=lambda: _env("DEFAULT_KEYWORD_METHOD", "mixed")
    )


settings = Settings()
