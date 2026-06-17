"""Persistence helpers for the Streamlit app and FastAPI backend supporting both MySQL and SQLite."""

from __future__ import annotations

import hashlib
import os
import time
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

try:
    import mysql.connector
    from mysql.connector import Error
    import mysql.connector.pooling
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    class Error(Exception):
        pass


def get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if key in st.secrets:
            val = st.secrets[key]
            if val is not None:
                return str(val)
    except Exception:
        pass
    return os.getenv(key, default)


DB_CONNECT_TIMEOUT = int(get_secret("MYSQL_CONNECT_TIMEOUT", "15"))
DB_RECONNECT_ATTEMPTS = int(get_secret("MYSQL_RECONNECT_ATTEMPTS", "2"))
DB_RECONNECT_DELAY = float(get_secret("MYSQL_RECONNECT_DELAY", "1"))

def get_db_config() -> dict[str, Any]:
    # Default config
    config = {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "ai_chatbot_db",
        "ssl_ca": None,
        "ssl_verify_cert": False
    }

    # 1. Try environment variables
    for key, cfg_key in [
        ("MYSQL_HOST", "host"),
        ("MYSQL_USER", "user"),
        ("MYSQL_PASSWORD", "password"),
        ("MYSQL_DATABASE", "database"),
    ]:
        val = os.getenv(key)
        if val is not None:
            config[cfg_key] = val

    port_val = os.getenv("MYSQL_PORT")
    if port_val is not None:
        try:
            config["port"] = int(port_val)
        except ValueError:
            pass

    ssl_ca_val = os.getenv("MYSQL_SSL_CA")
    if ssl_ca_val:
        config["ssl_ca"] = ssl_ca_val
    if os.getenv("MYSQL_SSL_VERIFY"):
        config["ssl_verify_cert"] = os.getenv("MYSQL_SSL_VERIFY").lower() in ("true", "1")

    # 2. Try Streamlit secrets
    try:
        import streamlit as st
        for key, cfg_key in [
            ("MYSQL_HOST", "host"),
            ("MYSQL_USER", "user"),
            ("MYSQL_PASSWORD", "password"),
            ("MYSQL_DATABASE", "database"),
        ]:
            if key in st.secrets:
                config[cfg_key] = st.secrets[key]
        if "MYSQL_PORT" in st.secrets:
            try:
                config["port"] = int(st.secrets["MYSQL_PORT"])
            except ValueError:
                pass
        if "MYSQL_SSL_CA" in st.secrets:
            config["ssl_ca"] = st.secrets["MYSQL_SSL_CA"]
        if "MYSQL_SSL_VERIFY" in st.secrets:
            val = st.secrets["MYSQL_SSL_VERIFY"]
            if isinstance(val, bool):
                config["ssl_verify_cert"] = val
            else:
                config["ssl_verify_cert"] = str(val).lower() in ("true", "1")
    except Exception:
        pass

    return config


_temp_ssl_ca_path = None

def get_ssl_ca_path(ssl_ca_content: str | None) -> str | None:
    global _temp_ssl_ca_path
    if not ssl_ca_content:
        return None
    
    # If it is a file path that exists, return it
    if os.path.exists(ssl_ca_content):
        return ssl_ca_content

    # If it looks like a PEM certificate content, write it to a temp file
    if "-----BEGIN CERTIFICATE-----" in ssl_ca_content:
        if _temp_ssl_ca_path and os.path.exists(_temp_ssl_ca_path):
            return _temp_ssl_ca_path
        
        import tempfile
        try:
            fd, path = tempfile.mkstemp(suffix="_aiven_ca.pem", text=True)
            with os.fdopen(fd, "w") as f:
                f.write(ssl_ca_content.strip())
            _temp_ssl_ca_path = path
            return path
        except Exception as e:
            print(f"Error creating temp SSL CA file: {e}")
            return None
            
    return None


DB_CONFIG = get_db_config()
DB_HOST = DB_CONFIG["host"]
DB_PORT = DB_CONFIG["port"]
DB_USER = DB_CONFIG["user"]
DB_PASSWORD = DB_CONFIG["password"]
DB_NAME = DB_CONFIG["database"]

# Determine database mode
DB_TYPE = get_secret("DB_TYPE", "").lower()
USE_SQLITE = False

if not MYSQL_AVAILABLE or DB_TYPE == "sqlite":
    USE_SQLITE = True
elif DB_CONFIG["host"] in ("127.0.0.1", "localhost"):
    try:
        # Short timeout to detect if local MySQL server is running
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            connection_timeout=2,
        )
        conn.close()
    except Exception:
        USE_SQLITE = True
else:
    # Remote DB host explicitly set, so assume MySQL should be used
    USE_SQLITE = False


class SQLiteCursorWrapper:
    def __init__(self, cursor, dictionary=False):
        self.cursor = cursor
        self.dictionary = dictionary

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute(self, query, params=None):
        # Translate placeholder %s to ?
        query = query.replace("%s", "?")
        # Handle ON DUPLICATE KEY UPDATE in google_credentials
        if "ON DUPLICATE KEY UPDATE" in query:
            query = """
            INSERT INTO google_credentials (user_id, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = COALESCE(NULLIF(excluded.refresh_token, ''), refresh_token),
                expires_at = excluded.expires_at
            """
        if params is None:
            self.cursor.execute(query)
        else:
            self.cursor.execute(query, params)
        return self

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        if self.dictionary:
            return dict(row)
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.dictionary:
            return [dict(row) for row in rows]
        return rows

    def close(self):
        self.cursor.close()


class SQLiteConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

    def cursor(self, dictionary=False):
        cursor = self.conn.cursor()
        return SQLiteCursorWrapper(cursor, dictionary=dictionary)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def is_connected(self):
        return True

    def ping(self, *args, **kwargs):
        pass

    def reconnect(self, *args, **kwargs):
        pass


def sqlite_connection():
    db_path = get_secret("SQLITE_DATABASE_PATH", "ai_chatbot.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable foreign key constraint enforcement in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return SQLiteConnectionWrapper(conn)


SQLITE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login_at DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT 'New chat',
        provider TEXT NULL,
        model_name TEXT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        role TEXT CHECK(role IN ('user', 'assistant')) NOT NULL,
        content TEXT NOT NULL,
        snippet TEXT NULL,
        image_mime TEXT NULL,
        image_data BLOB NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        conversation_id INTEGER NULL,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        mime_type TEXT NULL,
        source TEXT NOT NULL DEFAULT 'chat_upload',
        text_content TEXT NULL,
        data_json TEXT NULL,
        data_preview TEXT NULL,
        image_data BLOB NULL,
        rows_count INTEGER NULL,
        columns_count INTEGER NULL,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS voice_transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        conversation_id INTEGER NULL,
        mime_type TEXT NOT NULL DEFAULT 'audio/wav',
        audio_data BLOB NULL,
        model_name TEXT NULL,
        transcript TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NULL,
        provider TEXT NOT NULL,
        model_name TEXT NULL,
        prompt TEXT NULL,
        response TEXT NULL,
        status TEXT NOT NULL DEFAULT 'success',
        error_message TEXT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS google_credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        access_token TEXT NOT NULL,
        refresh_token TEXT NOT NULL,
        expires_at REAL NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """
]


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash CHAR(64) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        title VARCHAR(255) NOT NULL DEFAULT 'New chat',
        provider VARCHAR(50) NULL,
        model_name VARCHAR(120) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_conversations_user_updated (user_id, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        conversation_id INT NOT NULL,
        role ENUM('user', 'assistant') NOT NULL,
        content MEDIUMTEXT NOT NULL,
        snippet TEXT NULL,
        image_mime VARCHAR(100) NULL,
        image_data MEDIUMBLOB NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
        INDEX idx_messages_conversation_created (conversation_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS uploads (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        conversation_id INT NULL,
        filename VARCHAR(255) NOT NULL,
        file_type VARCHAR(40) NOT NULL,
        mime_type VARCHAR(120) NULL,
        source VARCHAR(40) NOT NULL DEFAULT 'chat_upload',
        text_content MEDIUMTEXT NULL,
        data_json LONGTEXT NULL,
        data_preview MEDIUMTEXT NULL,
        image_data MEDIUMBLOB NULL,
        rows_count INT NULL,
        columns_count INT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        INDEX idx_uploads_user_uploaded (user_id, uploaded_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS voice_transcriptions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        conversation_id INT NULL,
        mime_type VARCHAR(100) NOT NULL DEFAULT 'audio/wav',
        audio_data MEDIUMBLOB NULL,
        model_name VARCHAR(120) NULL,
        transcript MEDIUMTEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        INDEX idx_voice_user_created (user_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS api_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        conversation_id INT NULL,
        provider VARCHAR(50) NOT NULL,
        model_name VARCHAR(120) NULL,
        prompt MEDIUMTEXT NULL,
        response MEDIUMTEXT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'success',
        error_message TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        INDEX idx_api_logs_conversation_created (conversation_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS google_credentials (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL UNIQUE,
        access_token TEXT NOT NULL,
        refresh_token TEXT NOT NULL,
        expires_at DOUBLE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def connect_with_retries(connect_fn):
    last_error = None
    for attempt in range(1, DB_RECONNECT_ATTEMPTS + 1):
        try:
            conn = connect_fn()
            if conn.is_connected():
                return conn
        except Error as ex:
            last_error = ex
            if attempt < DB_RECONNECT_ATTEMPTS:
                time.sleep(DB_RECONNECT_DELAY)
            else:
                raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to connect to MySQL")


def get_mysql_connect_params(timeout: int = 15) -> dict[str, Any]:
    params = {
        "host": DB_CONFIG["host"],
        "port": DB_CONFIG["port"],
        "user": DB_CONFIG["user"],
        "password": DB_CONFIG["password"],
        "database": DB_CONFIG["database"],
        "connection_timeout": timeout,
        "raise_on_warnings": False,
    }
    
    # Process SSL CA path
    ssl_ca = get_ssl_ca_path(DB_CONFIG.get("ssl_ca"))
    if ssl_ca:
        params["ssl_ca"] = ssl_ca
        params["ssl_verify_cert"] = DB_CONFIG.get("ssl_verify_cert", False)
        
    return params


def server_connection():
    if USE_SQLITE:
        return sqlite_connection()
    params = get_mysql_connect_params(DB_CONNECT_TIMEOUT)
    if "database" in params:
        del params["database"]
    return connect_with_retries(lambda: mysql.connector.connect(**params))


_connection_pool = None


def get_connection_pool():
    global _connection_pool
    if USE_SQLITE:
        return None
    if _connection_pool is None:
        try:
            params = get_mysql_connect_params(DB_CONNECT_TIMEOUT)
            _connection_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="ai_chatbot_pool",
                pool_size=10,
                **params
            )
        except Exception:
            _connection_pool = None
    return _connection_pool


def database_connection():
    if USE_SQLITE:
        return sqlite_connection()
    pool = get_connection_pool()
    if pool is not None:
        try:
            return pool.get_connection()
        except mysql.connector.Error:
            pass

    params = get_mysql_connect_params(DB_CONNECT_TIMEOUT)
    return connect_with_retries(lambda: mysql.connector.connect(**params))


def reconnect_connection(conn):
    if USE_SQLITE or conn is None:
        return conn
    try:
        # Ping the server and attempt to reconnect if the connection has timed out or closed
        conn.ping(reconnect=True, attempts=DB_RECONNECT_ATTEMPTS, delay=DB_RECONNECT_DELAY)
    except Exception:
        try:
            conn.reconnect(attempts=DB_RECONNECT_ATTEMPTS, delay=DB_RECONNECT_DELAY)
        except Exception:
            pass
    return conn


@contextmanager
def get_connection():
    conn = database_connection()
    conn = reconnect_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        if conn is not None and conn.is_connected():
            conn.rollback()
        raise
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


def init_database() -> None:
    if USE_SQLITE:
        with sqlite_connection() as conn:
            cursor = conn.cursor()
            for statement in SQLITE_SCHEMA_STATEMENTS:
                cursor.execute(statement)
            cursor.close()
        return

    with server_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
        cursor.close()

    with get_connection() as conn:
        cursor = conn.cursor()
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        cursor.close()


def ensure_user(username: str, password: str) -> int:
    password_hash = hash_password(password)
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET password_hash = %s, last_login_at = %s WHERE id = %s",
                (password_hash, datetime.now(), row["id"]),
            )
            user_id = int(row["id"])
        else:
            cursor.execute(
                "INSERT INTO users (username, password_hash, last_login_at) VALUES (%s, %s, %s)",
                (username, password_hash, datetime.now()),
            )
            user_id = int(cursor.lastrowid)
        cursor.close()
        return user_id


def check_user_exists(username: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()
        return row is not None


def verify_user(username: str, password: str) -> int | None:
    password_hash = hash_password(password)
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row and row["password_hash"] == password_hash:
            cursor.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (datetime.now(), row["id"]),
            )
            user_id = int(row["id"])
            cursor.close()
            return user_id
        cursor.close()
        return None


def create_user(username: str, password: str) -> int:
    password_hash = hash_password(password)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, last_login_at) VALUES (%s, %s, %s)",
            (username, password_hash, datetime.now()),
        )
        user_id = int(cursor.lastrowid)
        cursor.close()
        return user_id


def get_user_id(username: str) -> int | None:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()
        return int(row["id"]) if row else None



def create_conversation(user_id: int, title: str = "New chat", provider: str = "", model_name: str = "") -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (user_id, title, provider, model_name) VALUES (%s, %s, %s, %s)",
            (user_id, title, provider or None, model_name or None),
        )
        conversation_id = int(cursor.lastrowid)
        cursor.close()
        return conversation_id


def update_conversation(conversation_id: int, title: str, provider: str = "", model_name: str = "") -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE conversations
            SET title = %s, provider = COALESCE(NULLIF(%s, ''), provider),
                model_name = COALESCE(NULLIF(%s, ''), model_name), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (title, provider, model_name, conversation_id),
        )
        cursor.close()


def list_conversations(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at
            FROM conversations c
            WHERE c.user_id = %s
              AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows


def load_messages(conversation_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT role, content, snippet, image_mime, image_data AS img
            FROM messages
            WHERE conversation_id = %s
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows


def save_message(
    conversation_id: int,
    role: str,
    content: str,
    snippet: str | None = None,
    image_data: bytes | None = None,
    image_mime: str | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (conversation_id, role, content, snippet, image_mime, image_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (conversation_id, role, content, snippet, image_mime, image_data),
        )
        message_id = int(cursor.lastrowid)
        cursor.close()
        return message_id


def clear_conversation_messages(conversation_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
        cursor.close()


def save_upload(
    user_id: int,
    conversation_id: int | None,
    filename: str,
    file_type: str,
    mime_type: str = "",
    source: str = "chat_upload",
    text_content: str | None = None,
    dataframe: Any = None,
    image_data: bytes | None = None,
) -> int:
    data_json = None
    data_preview = None
    rows_count = None
    columns_count = None
    if dataframe is not None:
        data_json = dataframe.to_json(orient="records", date_format="iso")
        data_preview = dataframe.head(50).to_csv(index=False)
        rows_count = int(dataframe.shape[0])
        columns_count = int(dataframe.shape[1])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO uploads (
                user_id, conversation_id, filename, file_type, mime_type, source,
                text_content, data_json, data_preview, image_data, rows_count, columns_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                conversation_id,
                filename,
                file_type,
                mime_type or None,
                source,
                text_content,
                data_json,
                data_preview,
                image_data,
                rows_count,
                columns_count,
            ),
        )
        upload_id = int(cursor.lastrowid)
        cursor.close()
        return upload_id


def save_voice_transcription(
    user_id: int,
    conversation_id: int | None,
    transcript: str,
    model_name: str = "",
    mime_type: str = "audio/wav",
    audio_data: bytes | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO voice_transcriptions
                (user_id, conversation_id, mime_type, audio_data, model_name, transcript)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, conversation_id, mime_type, audio_data, model_name or None, transcript),
        )
        row_id = int(cursor.lastrowid)
        cursor.close()
        return row_id


def save_api_log(
    conversation_id: int | None,
    provider: str,
    model_name: str,
    prompt: str,
    response: str = "",
    status: str = "success",
    error_message: str = "",
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_logs
                (conversation_id, provider, model_name, prompt, response, status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                conversation_id,
                provider,
                model_name or None,
                prompt,
                response,
                status,
                error_message or None,
            ),
        )
        row_id = int(cursor.lastrowid)
        cursor.close()
        return row_id


def load_conversation_uploads(conversation_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT filename, file_type, mime_type, text_content, data_json, image_data
            FROM uploads
            WHERE conversation_id = %s
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows


def delete_conversation(conversation_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        cursor.close()


def load_user_uploads(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, conversation_id, filename, file_type, mime_type, source,
                   rows_count, columns_count, uploaded_at
            FROM uploads
            WHERE user_id = %s
            ORDER BY uploaded_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows


def load_upload_content(upload_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, filename, file_type, mime_type, text_content, data_json, image_data
            FROM uploads
            WHERE id = %s
            """,
            (upload_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return row


def delete_upload(upload_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM uploads WHERE id = %s", (upload_id,))
        cursor.close()


def save_google_credentials(user_id: int, access_token: str, refresh_token: str, expires_at: float) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO google_credentials (user_id, access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = COALESCE(NULLIF(VALUES(refresh_token), ''), refresh_token),
                expires_at = VALUES(expires_at)
            """,
            (user_id, access_token, refresh_token, expires_at),
        )
        cursor.close()


def load_google_credentials(user_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT access_token, refresh_token, expires_at FROM google_credentials WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return row


def delete_google_credentials(user_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM google_credentials WHERE user_id = %s", (user_id,))
        cursor.close()


def database_status() -> dict[str, str]:
    try:
        init_database()
        if USE_SQLITE:
            db_path = get_secret("SQLITE_DATABASE_PATH", "ai_chatbot.db")
            return {"ok": "true", "database": f"SQLite ({db_path})", "host": "local"}
        return {"ok": "true", "database": DB_NAME, "host": DB_HOST}
    except Exception as ex:
        return {"ok": "false", "error": str(ex), "database": DB_NAME, "host": DB_HOST}
