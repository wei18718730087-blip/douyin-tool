from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    output_dir: str = "./downloads"
    default_keyword_count: int = 20
    default_keyword_method: str = "mixed"

    model_config = {"env_prefix": "DOUYIN_", "env_file": ".env"}


settings = Settings()
