"""
=============================================================
Step 12 -- Generate Vector Embeddings for Schema Metadata
=============================================================
Reads the 'description' column from schema_metadata, generates
384-dimensional embeddings using all-MiniLM-L6-v2, and stores
them in the pgvector VECTOR(384) 'embedding' column.

Only processes rows where embedding IS NULL (safe to re-run).

Usage:
    python embed_schema.py
=============================================================
"""

import psycopg2
from sentence_transformers import SentenceTransformer
from config import DB_CONFIG, EMBEDDING_MODEL


def main():
    print("=" * 60)
    print("  Wargame Schema Embedding Generator")
    print("=" * 60)

    # 1. Connect to database
    print("\nConnecting to database '%s'..." % DB_CONFIG["dbname"])
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print("  [OK] Connected")

    # 2. Load the embedding model
    print("\nLoading embedding model: %s" % EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("  [OK] Model loaded (dimension: %d)" % model.get_sentence_embedding_dimension())

    # 3. Fetch all rows that need embeddings
    cursor.execute(
        "SELECT metadata_id, description FROM schema_metadata WHERE embedding IS NULL;"
    )
    rows = cursor.fetchall()

    if not rows:
        print("\n  All descriptions already have embeddings. Nothing to do.")
    else:
        print("\n  Generating embeddings for %d descriptions..." % len(rows))

        # Batch-encode all descriptions at once (much faster than one by one)
        ids = [row[0] for row in rows]
        descriptions = [row[1] for row in rows]

        vectors = model.encode(descriptions, show_progress_bar=True)

        # Update each row in the database
        for metadata_id, vector in zip(ids, vectors):
            vector_list = vector.tolist()
            cursor.execute(
                "UPDATE schema_metadata SET embedding = %s WHERE metadata_id = %s;",
                (vector_list, metadata_id)
            )

        conn.commit()
        print("  [OK] %d embeddings saved to database" % len(rows))

    # 4. Verify
    cursor.execute("SELECT COUNT(*) FROM schema_metadata WHERE embedding IS NOT NULL;")
    embedded_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schema_metadata;")
    total_count = cursor.fetchone()[0]
    print("\n  Verification: %d / %d rows have embeddings" % (embedded_count, total_count))

    cursor.close()
    conn.close()
    print("\nDone. Connection closed.")


if __name__ == "__main__":
    main()
