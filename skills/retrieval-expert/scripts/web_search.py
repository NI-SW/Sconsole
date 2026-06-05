#!/usr/bin/env python3
"""Web data retrieval helper for retrieval expert."""
import sys
import os
import json
import argparse
import subprocess
import urllib.request
import urllib.parse
import socket

DEFAULT_PROXY = "http://192.168.34.4:7890"

def _resolve_proxy(proxy=None):
    """Resolve proxy: explicit > env > auto-detect."""
    if proxy:
        return proxy
    proxy = os.environ.get("SCONSOLE_PROXY", "")
    if proxy:
        return proxy
    try:
        socket.create_connection(("www.google.com", 443), timeout=3)
        return None
    except (socket.timeout, OSError):
        return DEFAULT_PROXY

def _build_opener(proxy=None):
    """Build urllib opener with optional proxy."""
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()

def fetch_url(url, timeout=30, headers=None, proxy=None):
    """Fetch URL content."""
    proxy = _resolve_proxy(proxy)
    default_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "text/html,application/json,*/*",
    }
    if headers:
        default_headers.update(headers)
    
    req = urllib.request.Request(url, headers=default_headers)
    opener = _build_opener(proxy)
    try:
        with opener.open(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[1].split(";")[0].strip()
            
            text = data.decode(encoding, errors="replace")
            return {
                "status": resp.status,
                "content_type": content_type,
                "content_length": len(data),
                "content": text[:50000],
                "url": url,
            }
    except Exception as e:
        return {"error": str(e), "url": url}

def api_request(url, method="GET", data=None, headers=None, timeout=30, proxy=None):
    """Make API request."""
    proxy = _resolve_proxy(proxy)
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    opener = _build_opener(proxy)
    
    try:
        with opener.open(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            return {"status": resp.status, "data": result}
    except Exception as e:
        return {"error": str(e), "url": url}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web retrieval helper")
    parser.add_argument("--proxy", help="HTTP proxy URL", default=None)
    sub = parser.add_subparsers(dest="action")
    
    fetch_p = sub.add_parser("fetch", help="Fetch URL content")
    fetch_p.add_argument("url", help="URL to fetch")
    fetch_p.add_argument("--timeout", type=int, default=30)
    
    api_p = sub.add_parser("api", help="API request")
    api_p.add_argument("url", help="API URL")
    api_p.add_argument("--method", default="GET")
    api_p.add_argument("--data", help="JSON data string")
    api_p.add_argument("--timeout", type=int, default=30)
    
    args = parser.parse_args()
    
    if args.action == "fetch":
        result = fetch_url(args.url, args.timeout, proxy=args.proxy)
    elif args.action == "api":
        data = json.loads(args.data) if args.data else None
        result = api_request(args.url, args.method, data, timeout=args.timeout, proxy=args.proxy)
    else:
        result = {"error": "Specify action: fetch or api"}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
