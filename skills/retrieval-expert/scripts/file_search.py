#!/usr/bin/env python3
"""File search helper for retrieval expert."""
import os
import sys
import json
import argparse
import re
from pathlib import Path

def search_files(root_dir, pattern=None, content_pattern=None, file_type=None, max_depth=None, limit=50):
    """Search files by name, content, or type."""
    results = []
    root = Path(root_dir)
    
    for item in root.rglob("*"):
        if max_depth and len(item.relative_to(root).parts) > max_depth:
            continue
        if not item.is_file():
            continue
            
        match = True
        
        # Filter by filename pattern
        if pattern and not re.search(pattern, item.name, re.IGNORECASE):
            match = False
        
        # Filter by file extension
        if file_type and item.suffix.lower() != f".{file_type.lower()}":
            match = False
        
        # Filter by content
        content_match = None
        if content_pattern and match:
            try:
                with open(item, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(content_pattern, line, re.IGNORECASE):
                            content_match = {"line": i, "text": line.strip()[:200]}
                            break
            except:
                match = False
        
        if match:
            stat = item.stat()
            result = {
                "path": str(item),
                "name": item.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
            if content_match:
                result["content_match"] = content_match
            results.append(result)
            
            if len(results) >= limit:
                break
    
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="File search helper")
    parser.add_argument("root_dir", help="Root directory to search")
    parser.add_argument("--pattern", help="Filename pattern (regex)")
    parser.add_argument("--content", help="Content pattern (regex)")
    parser.add_argument("--type", help="File extension (e.g. csv, json)")
    parser.add_argument("--max-depth", type=int, help="Max search depth")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    args = parser.parse_args()
    
    results = search_files(args.root_dir, args.pattern, args.content, args.type, args.max_depth, args.limit)
    print(json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2))
