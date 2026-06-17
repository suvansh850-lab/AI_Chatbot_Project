"""Script to test and verify connection to Aiven MySQL database (Windows safe text)."""

import sys
import os
from datetime import datetime

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import database
    from database import (
        init_database, 
        get_connection, 
        USE_SQLITE, 
        DB_HOST, 
        DB_PORT, 
        DB_NAME, 
        DB_USER
    )
    print("[OK] Successfully imported database module.")
except Exception as e:
    print(f"[ERROR] Failed to import database module: {e}")
    sys.exit(1)

def run_test():
    print("-" * 50)
    print("ANALYZING CONNECTION CONFIGURATION:")
    print(f"  Host: {DB_HOST}")
    print(f"  Port: {DB_PORT}")
    print(f"  User: {DB_USER}")
    print(f"  Database Name: {DB_NAME}")
    print(f"  Using SQLite Fallback?: {USE_SQLITE}")
    print("-" * 50)

    if USE_SQLITE:
        print("[WARNING] The database configuration is currently falling back to SQLite.")
        print("   If you want to connect to Aiven MySQL, ensure:")
        print("   1. You have configured MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.")
        print("   2. For local testing, configure these in `.streamlit/secrets.toml`.")
        print("   3. Your Aiven instance is running and has public IP access enabled (or your current IP allowed).")
        print("-" * 50)

    print("Attempting to connect to database and initialize schema...")
    try:
        init_database()
        print("[OK] Database initialized successfully!")
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        print("\nTroubleshooting tips:")
        print("  - Double check your host, user, password, and port in secrets.toml.")
        print("  - Check your Aiven console. Under the 'Overview' tab, ensure 'Allowed IP addresses' is set to allow your current public IP (or set to 0.0.0.0/0 for open access).")
        print("  - Ensure that the SSL CA cert is correctly pasted under MYSQL_SSL_CA.")
        print("  - Ensure you have mysql-connector-python installed (pip install mysql-connector-python).")
        sys.exit(1)

    print("\nInspecting database tables:")
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            
            if USE_SQLITE:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row["name"] for row in cursor.fetchall()]
            else:
                cursor.execute("SHOW TABLES;")
                tables = [list(row.values())[0] for row in cursor.fetchall()]
                
            print(f"[OK] Connection successful! Found {len(tables)} tables:")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                count = cursor.fetchone()["cnt"]
                print(f"   - {table}: {count} records")
            
            cursor.close()
    except Exception as e:
        print(f"[ERROR] Failed to inspect tables: {e}")
        sys.exit(1)

    print("-" * 50)
    print("All database tests passed successfully! The configuration is ready for deployment.")
    print("-" * 50)

if __name__ == "__main__":
    run_test()
