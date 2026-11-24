"""
=============================================================
Wargame Analysis -- Centralized Configuration
=============================================================
All database credentials, model names, and settings live here.
No other file should hardcode these values.

To override, set environment variables:
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
    OLLAMA_URL
=============================================================
"""

import os

# ============================================================
# Database connection
# ============================================================
DB_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "dbname": os.environ.get("PGDATABASE", "wargame_analysis"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "123456"),
}

# ============================================================
# Embedding model (runs locally via sentence-transformers)
# ============================================================
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# ============================================================
# Ollama LLM settings (runs locally at localhost:11434)
# ============================================================
OLLAMA_BASE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
SQL_MODEL = "sqlcoder:7b"       # For generating SQL from natural language
ANSWER_MODEL = "mistral"      # For synthesizing natural language answers

# ============================================================
# RAG settings
# ============================================================
DEFAULT_TOP_K = 5             # Number of schema columns to retrieve per query
