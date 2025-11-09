import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_secret_token: str = os.environ.get("TELEGRAM_SECRET_TOKEN", "")
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
    google_credentials_json: str = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    google_sheet_id: str = os.environ.get("GOOGLE_SHEET_ID", "")
    google_sheet_range: str = os.environ.get("GOOGLE_SHEET_RANGE", "Ответы!A:Z")
    gas_endpoint: str = os.environ.get("GAS_ENDPOINT", "")
    pdf_font_path: str = os.environ.get("PDF_FONT_PATH", "")
    consultation_url: str = os.environ.get("CONSULTATION_URL", "")
    webhook_url: str = os.environ.get("WEBHOOK_URL", "")


settings = Settings()
