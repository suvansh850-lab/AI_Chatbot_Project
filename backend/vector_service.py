"""Vector database service to index and search document segments using ChromaDB and Gemini embeddings."""

import os
import sys
from typing import List

# Avoid relative import issues
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Directory where ChromaDB indices will be stored persistently
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db"))
os.makedirs(DB_PATH, exist_ok=True)

# Initialize ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=DB_PATH)


def get_api_key() -> str:
    """Helper to fetch Gemini API key from environment or secrets."""
    # Try environment variable
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        return api_key

    # Try backend config
    try:
        from backend.config import GEMINI_API_KEY as cfg_key
        if cfg_key and cfg_key != "YOUR_GEMINI_API_KEY_HERE":
            return cfg_key
    except Exception:
        pass

    # Try database get_secret (which reads streamlit secrets)
    try:
        from database import get_secret
        st_key = get_secret("GEMINI_API_KEY", "")
        if st_key and st_key != "YOUR_GEMINI_API_KEY_HERE":
            return st_key
    except Exception:
        pass

    return ""


class GeminiDocumentEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function for ChromaDB index operations using Gemini."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)

    def __call__(self, input: Documents) -> Embeddings:
        import google.generativeai as genai
        try:
            response = genai.embed_content(
                model="models/gemini-embedding-001",
                content=input,
                task_type="retrieval_document"
            )
            return response["embedding"]
        except Exception as e:
            print(f"Error generating document embeddings: {e}")
            raise e


def get_query_embedding(query: str, api_key: str) -> List[float]:
    """Generates a query-specific embedding from Gemini."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    try:
        response = genai.embed_content(
            model="models/gemini-embedding-001",
            content=query,
            task_type="retrieval_query"
        )
        return response["embedding"]
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        raise e


def index_document(conversation_id: int, file_name: str, text_content: str) -> bool:
    """Chunks text and adds the documents with embeddings to a ChromaDB collection."""
    if not text_content or not text_content.strip():
        return False

    api_key = get_api_key()
    if not api_key:
        print("Warning: GEMINI_API_KEY is not configured. Skipping ChromaDB indexing.")
        return False

    try:
        # Create or fetch ChromaDB collection named after the conversation
        embedding_fn = GeminiDocumentEmbeddingFunction(api_key)
        collection = chroma_client.get_or_create_collection(
            name=f"conv_{conversation_id}",
            embedding_function=embedding_fn
        )

        # Split text content into small chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        chunks = text_splitter.split_text(text_content)

        documents = []
        ids = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            if chunk.strip():
                documents.append(chunk)
                ids.append(f"doc_{conversation_id}_{idx}")
                metadatas.append({"file_name": file_name, "chunk_index": idx})

        if documents:
            collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas
            )
            print(f"Successfully indexed '{file_name}' ({len(documents)} chunks) in ChromaDB.")
            return True
    except Exception as e:
        print(f"ChromaDB indexing error for '{file_name}': {e}")
    return False


def query_relevant_context(conversation_id: int, query: str, top_k: int = 5) -> str:
    """Queries ChromaDB for segments similar to the query string."""
    if not query or not query.strip():
        return ""

    api_key = get_api_key()
    if not api_key:
        return ""

    try:
        # Check if the collection exists
        collection_name = f"conv_{conversation_id}"
        # ChromaDB client.get_collection throws an exception if the collection doesn't exist
        embedding_fn = GeminiDocumentEmbeddingFunction(api_key)
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_fn
        )

        # Generate query embedding with optimal query retrieval task_type
        query_emb = get_query_embedding(query, api_key)

        # Query matching vectors
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=top_k
        )

        matched_chunks = results.get("documents", [[]])[0]
        if matched_chunks:
            return "\n\n".join(matched_chunks)
    except Exception:
        # Silence exception since collection might not exist (e.g. no documents uploaded yet)
        pass

    return ""
