"""
=============================================================
RAG Retrieval Layer -- Vector Similarity Search
=============================================================
Converts a user question into an embedding and finds the most
relevant schema columns using pgvector cosine distance search.

The SentenceTransformer model is loaded once and reused across
all search calls (singleton pattern).

Usage:
    # As a module:
    from vector_search import search_schema
    results = search_schema("Which ship has the lowest fuel?")

    # Standalone test (Step 13):
    python vector_search.py
=============================================================
"""

import psycopg2
from sentence_transformers import SentenceTransformer
from config import DB_CONFIG, EMBEDDING_MODEL, DEFAULT_TOP_K

# ============================================================
# Singleton model instance -- loaded once, reused across calls
# ============================================================
_model = None

import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _get_model():
    """Load the embedding model once and cache it."""
    global _model
    if _model is None:
        print("  Loading embedding model (one-time)...")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def get_db_connection():
    """Establishes a connection to PostgreSQL using centralized config."""
    return psycopg2.connect(**DB_CONFIG)


def search_schema(user_question, limit=None):
    """
    Converts a question into an embedding and queries schema_metadata
    via pgvector cosine distance to find the most relevant columns.

    Args:
        user_question: Natural language question from the user.
        limit: Number of results to return (default from config).

    Returns:
        List of (table_name, column_name, description, distance) tuples.
        Lower distance = more relevant.
    """
    if limit is None:
        limit = DEFAULT_TOP_K

    model = _get_model()
    query_vector = model.encode(user_question).tolist()

    # pgvector cosine distance operator: <=>
    # Lower values = more similar
    search_sql = """
        SELECT table_name, column_name, description,
               embedding <=> %s::vector AS distance
        FROM schema_metadata
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(search_sql, (query_vector, query_vector, limit))
            return cursor.fetchall()
    except Exception as e:
        print("  [ERROR] Database query failed: %s" % str(e))
        return []
    finally:
        if conn:
            conn.close()


# ============================================================
# Step 13 -- Standalone test
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  Step 13 -- RAG Vector Search Test")
    print("=" * 60)

    test_questions = [
        "Which submarine has the most fuel remaining?",
        "What is the hull damage on Red force ships?",
        "Show me all radar detections in Zone Alpha",
        "How many missiles were fired during the battle?",
        "What messages did Blue force send?",
    ]

    for q in test_questions:
        print("\nQuestion: %s" % q)
        print("-" * 50)
        results = search_schema(q, limit=5)

        if not results:
            print("  No results. Run embed_schema.py first.")
        else:
            for table, column, description, distance in results:
                # Truncate long descriptions for readability
                short_desc = description[:80] + "..." if len(description) > 80 else description
                print("  [%.4f] %s.%s" % (distance, table, column))
                print("           %s" % short_desc)

    print("\n" + "=" * 60)
    print("  Test complete. If distances are 0.3-0.8, RAG is working.")
    print("=" * 60)
