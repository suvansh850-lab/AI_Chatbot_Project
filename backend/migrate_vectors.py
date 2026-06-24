"""Script to backfill/migrate existing documents in SQLite/MySQL uploads table into ChromaDB."""

import os
import sys

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_connection
from backend.vector_service import index_document

def migrate_existing_uploads_to_vector_db():
    print("Starting migration of existing uploads to Vector DB...")
    
    uploads = []
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            # Fetch all uploaded documents containing text
            cursor.execute(
                "SELECT id, conversation_id, filename, text_content "
                "FROM uploads "
                "WHERE file_type = 'document' AND text_content IS NOT NULL"
            )
            uploads = cursor.fetchall()
            cursor.close()
    except Exception as db_err:
        print(f"Error querying database: {db_err}")
        return
        
    if not uploads:
        print("No documents found in database to migrate.")
        return

    print(f"Found {len(uploads)} document(s) in relational database.")
    migrated_count = 0
    for file in uploads:
        conv_id = file["conversation_id"]
        filename = file["filename"]
        text = file["text_content"]
        
        if not conv_id:
            print(f"Skipping '{filename}' (ID: {file['id']}) - no conversation ID associated.")
            continue
            
        print(f"Embedding and migrating '{filename}' for Chat ID: {conv_id}...")
        try:
            success = index_document(conversation_id=conv_id, file_name=filename, text_content=text)
            if success:
                migrated_count += 1
            else:
                print(f"Warning: Indexing returned False for '{filename}'.")
        except Exception as e:
            print(f"Failed to migrate '{filename}': {e}")
            
    print(f"Migration completed! Successfully indexed {migrated_count} of {len(uploads)} documents.")

if __name__ == "__main__":
    migrate_existing_uploads_to_vector_db()
