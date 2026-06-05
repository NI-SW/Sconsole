#!/usr/bin/env python3
"""Database query helper for retrieval expert."""
import sys
import subprocess
import json
import argparse

# Default: use host.containers.internal for Docker/Podman container access
DEFAULT_HOST = "host.containers.internal"
DEFAULT_PORT = "3306"
DEFAULT_USER = "root"
DEFAULT_PASS = "Info@1234"
DEFAULT_DB = "SCL_sconsole"

def query(sql, host=DEFAULT_HOST, port=DEFAULT_PORT, user=DEFAULT_USER, 
          password=DEFAULT_PASS, database=DEFAULT_DB, format="json"):
    """Execute SQL query and return formatted results."""
    cmd = [
        "mysql", f"-h{host}", f"-P{port}", f"-u{user}", 
        f"-p{password}", database, "-e", sql, "--batch", "--raw"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "sql": sql}
        
        lines = result.stdout.strip().split("\n")
        if not lines or len(lines) == 0:
            return {"results": [], "count": 0, "sql": sql}
        
        headers = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            values = line.split("\t")
            row = dict(zip(headers, values))
            rows.append(row)
        
        return {"results": rows, "count": len(rows), "sql": sql}
    except subprocess.TimeoutExpired:
        return {"error": "Query timeout (30s)", "sql": sql}
    except Exception as e:
        return {"error": str(e), "sql": sql}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database query helper")
    parser.add_argument("sql", help="SQL query to execute")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASS)
    parser.add_argument("--database", default=DEFAULT_DB)
    parser.add_argument("--format", choices=["table", "json"], default="json")
    args = parser.parse_args()
    
    result = query(args.sql, args.host, args.port, args.user, args.password, args.database, args.format)
    print(json.dumps(result, ensure_ascii=False, indent=2))
