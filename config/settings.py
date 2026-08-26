"""
Configuration settings for BPS RAG Ingestion and Extraction Pipeline.
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data_publikasi"
    DEMAK_DATA_DIR: Path = DATA_DIR / "demak"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    DATABASE_DIR: Path = PROJECT_ROOT / "database"

    # SQLite metadata and document registry
    REGISTRY_DB_PATH: Path = DATABASE_DIR / "bps_registry.db"
    DOCUMENT_DB_PATH: Path = DATABASE_DIR / "bps_documents.json"
    VECTOR_DB_DIR: Path = DATABASE_DIR / "chroma_store"

    # BPS Target configuration
    BPS_BASE_URL: str = "https://demakkab.bps.go.id"
    BPS_PUBLICATION_PATH: str = "/id/publication"
    BPS_CENTRAL_URL: str = "https://www.bps.go.id"
    DEFAULT_REGION: str = "Kabupaten Demak"
    DEFAULT_REGION_CODE: str = "3321"  # Demak BPS Area Code

    # Ingestion configuration
    REQUEST_TIMEOUT: int = 30
    MAX_DOWNLOAD_RETRIES: int = 3
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 (BPS Data Ingestion Bot)"
    )

    # Extraction configuration
    MIN_TABLE_ROWS: int = 2
    MIN_TABLE_COLS: int = 2
    HEADER_MAX_SCAN_ROWS: int = 4  # Max header depth to check for multi-level headers

    # Embedding & Vector configuration
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_COLLECTION_NAME: str = "bps_demak_knowledge"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    class Config:
        env_file = ".env"
        extra = "allow"


# Instantiate singleton settings
settings = Settings()

# Ensure directories exist
settings.DEMAK_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.DATABASE_DIR.mkdir(parents=True, exist_ok=True)
