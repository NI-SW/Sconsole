#!/usr/bin/env python3
"""GitHub search helper - search repos, code, issues, and users via GitHub API."""
import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
import socket

GITHUB_API = "https://api.github.com"
DEFAULT_PROXY = "http://192.168.34.4:7890"

def _test_direct_connect(host="api.github.com", port=443, timeout=5):
    """Test if we can directly reach GitHub API."""
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except (socket.timeout, OSError):
        return False

def _resolve_proxy(proxy=None):
    """Resolve proxy: explicit > env > auto-detect > default."""
    if proxy:
        return proxy
    proxy = os.environ.get("SCONSOLE_PROXY", "")
    if proxy:
        return proxy
    if not _test_direct_connect():
        return DEFAULT_PROXY
    return None

def github_request(endpoint, params=None, token=None, proxy=None):
    """Make a GitHub API request."""
    proxy = _resolve_proxy(proxy)
    url = f"{GITHUB_API}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Sconsole-RetrievalExpert/1.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    
    req = urllib.request.Request(url, headers=headers)
    
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    
    try:
        with opener.open(req, timeout=30) as resp:
            # Handle pagination
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            reset = resp.headers.get("X-RateLimit-Reset", "?")
            
            data = json.loads(resp.read().decode())
            return {
                "status": resp.status,
                "data": data,
                "rate_limit_remaining": remaining,
                "rate_limit_reset": reset,
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {e.reason}", "detail": body[:500]}
    except Exception as e:
        return {"error": str(e)}

def search_repos(query, sort="stars", order="desc", limit=10, token=None, proxy=None):
    """Search GitHub repositories."""
    params = {"q": query, "sort": sort, "order": order, "per_page": min(limit, 100)}
    result = github_request("/search/repositories", params, token, proxy)
    if "error" in result:
        return result
    
    items = result.get("data", {}).get("items", [])[:limit]
    repos = []
    for item in items:
        repos.append({
            "name": item.get("full_name"),
            "description": item.get("description", "")[:200],
            "stars": item.get("stargazers_count"),
            "language": item.get("language"),
            "url": item.get("html_url"),
            "topics": item.get("topics", []),
            "updated": item.get("updated_at"),
        })
    return {"results": repos, "total": result.get("data", {}).get("total_count", 0)}

def search_code(query, limit=10, token=None, proxy=None):
    """Search GitHub code."""
    params = {"q": query, "per_page": min(limit, 100)}
    result = github_request("/search/code", params, token, proxy)
    if "error" in result:
        return result
    
    items = result.get("data", {}).get("items", [])[:limit]
    code_results = []
    for item in items:
        code_results.append({
            "file": item.get("name"),
            "repo": item.get("repository", {}).get("full_name"),
            "path": item.get("path"),
            "url": item.get("html_url"),
        })
    return {"results": code_results, "total": result.get("data", {}).get("total_count", 0)}

def search_issues(query, limit=10, token=None, proxy=None):
    """Search GitHub issues and PRs."""
    params = {"q": query, "per_page": min(limit, 100)}
    result = github_request("/search/issues", params, token, proxy)
    if "error" in result:
        return result
    
    items = result.get("data", {}).get("items", [])[:limit]
    issues = []
    for item in items:
        issues.append({
            "title": item.get("title"),
            "state": item.get("state"),
            "type": "PR" if "pull_request" in item else "Issue",
            "repo": item.get("repository_url", "").split("repos/")[-1],
            "url": item.get("html_url"),
            "labels": [l.get("name") for l in item.get("labels", [])],
            "created": item.get("created_at"),
        })
    return {"results": issues, "total": result.get("data", {}).get("total_count", 0)}

def get_readme(owner_repo, token=None, proxy=None):
    """Get README content of a repository."""
    result = github_request(f"/repos/{owner_repo}/readme", token=token, proxy=proxy)
    if "error" in result:
        return result
    
    import base64
    data = result.get("data", {})
    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    return {
        "repo": owner_repo,
        "content": content[:20000],  # Limit to 20KB
        "encoding": data.get("encoding"),
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub search helper")
    parser.add_argument("--token", help="GitHub personal access token")
    parser.add_argument("--proxy", help="HTTP proxy URL")
    sub = parser.add_subparsers(dest="action")
    
    repo_p = sub.add_parser("repos", help="Search repositories")
    repo_p.add_argument("query", help="Search query")
    repo_p.add_argument("--sort", default="stars", choices=["stars", "forks", "updated"])
    repo_p.add_argument("--limit", type=int, default=10)
    
    code_p = sub.add_parser("code", help="Search code")
    code_p.add_argument("query", help="Search query")
    code_p.add_argument("--limit", type=int, default=10)
    
    issues_p = sub.add_parser("issues", help="Search issues/PRs")
    issues_p.add_argument("query", help="Search query")
    issues_p.add_argument("--limit", type=int, default=10)
    
    readme_p = sub.add_parser("readme", help="Get repo README")
    readme_p.add_argument("repo", help="owner/repo format")
    
    args = parser.parse_args()
    
    if args.action == "repos":
        result = search_repos(args.query, args.sort, limit=args.limit, token=args.token, proxy=args.proxy)
    elif args.action == "code":
        result = search_code(args.query, limit=args.limit, token=args.token, proxy=args.proxy)
    elif args.action == "issues":
        result = search_issues(args.query, limit=args.limit, token=args.token, proxy=args.proxy)
    elif args.action == "readme":
        result = get_readme(args.repo, token=args.token, proxy=args.proxy)
    else:
        result = {"error": "Specify action: repos, code, issues, readme"}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
