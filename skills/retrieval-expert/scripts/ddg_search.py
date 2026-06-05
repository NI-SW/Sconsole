#!/usr/bin/env python3
"""DuckDuckGo search helper - privacy-focused web search."""
import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
import re
import socket

DEFAULT_PROXY = "http://192.168.34.4:7890"
CONNECT_TIMEOUT = 15

def _test_direct_connect(host="html.duckduckgo.com", port=443, timeout=5):
    """Test if we can directly reach DuckDuckGo."""
    try:
        socket.create_connection((host, port), timeout=timeout)
        return True
    except (socket.timeout, OSError):
        return False

def _build_opener(proxy=None):
    """Build urllib opener with optional proxy."""
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()

def ddg_search(query, max_results=10, proxy=None):
    """Search DuckDuckGo HTML version and parse results."""
    # Auto-detect proxy: explicit > env > test direct > default proxy
    if proxy is None:
        proxy = os.environ.get("SCONSOLE_PROXY", "")
    if not proxy and not _test_direct_connect():
        proxy = DEFAULT_PROXY

    url = "https://html.duckduckgo.com/html/"
    params = urllib.parse.urlencode({"q": query})
    data = params.encode()

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    req = urllib.request.Request(url, data=data, headers=headers)
    opener = _build_opener(proxy if proxy else None)

    try:
        with opener.open(req, timeout=CONNECT_TIMEOUT + 15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        # If direct fails, retry with proxy
        if not proxy:
            try:
                opener = _build_opener(DEFAULT_PROXY)
                with opener.open(req, timeout=CONNECT_TIMEOUT + 15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as e2:
                return {"error": f"Direct and proxy both failed: {e}; {e2}", "query": query}
        else:
            return {"error": str(e), "query": query}

    # Parse results from HTML - use flexible patterns as DDG changes HTML structure
    results = []
    
    # Try pattern 1: classic result__a links (with or without nofollow)
    result_blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+?)"[^>]*>(.*?)</a>.*?'
        r'(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>.*?)?'
        r'(?:<a[^>]*class="result__url"[^>]*>(.*?)</a>)?',
        html, re.DOTALL
    )
    
    if not result_blocks:
        # Try pattern 2: newer DDG HTML with different class names
        result_blocks = re.findall(
            r'<a[^>]*class="[^"]*result[^"]*"[^>]*href="([^"]+?)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        result_blocks = [(url, title, '', '') for url, title in result_blocks]
    
    if not result_blocks:
        # Try pattern 3: any links with data from DDG
        result_blocks = re.findall(
            r'<a[^>]*href="(https?://[^"]+?)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        # Filter out DDG internal links
        result_blocks = [(url, title, '', '') for url, title in result_blocks 
                         if 'duckduckgo.com' not in url and 'javascript:' not in url.lower()]

    for url_match, title_match, snippet_match, domain_match in result_blocks:
        title = re.sub(r'<[^>]+>', '', title_match).strip()
        snippet = re.sub(r'<[^>]+>', '', snippet_match).strip()
        domain = re.sub(r'<[^>]+>', '', domain_match).strip()

        link = url_match
        if link.startswith("//"):
            link = "https:" + link

        results.append({
            "title": title,
            "url": link,
            "snippet": snippet,
            "domain": domain,
        })

        if len(results) >= max_results:
            break

    return {"results": results, "count": len(results), "query": query}

def ddg_instant_answer(query, proxy=None):
    """Get DuckDuckGo instant answer API results."""
    if proxy is None:
        proxy = os.environ.get("SCONSOLE_PROXY", "")
    if not proxy and not _test_direct_connect():
        proxy = DEFAULT_PROXY

    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 0,
    })

    headers = {"User-Agent": "Sconsole-RetrievalExpert/1.0"}
    req = urllib.request.Request(url, headers=headers)
    opener = _build_opener(proxy if proxy else None)

    try:
        with opener.open(req, timeout=CONNECT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        answer = {
            "abstract": data.get("AbstractText", ""),
            "abstract_source": data.get("AbstractSource", ""),
            "abstract_url": data.get("AbstractURL", ""),
            "definition": data.get("Definition", ""),
            "answer": data.get("Answer", ""),
            "answer_type": data.get("AnswerType", ""),
            "related_topics": [],
        }

        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and "Text" in topic:
                answer["related_topics"].append({
                    "text": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })

        return answer
    except Exception as e:
        if not proxy:
            try:
                opener = _build_opener(DEFAULT_PROXY)
                with opener.open(req, timeout=CONNECT_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode())
                # same parsing as above, simplified return
                return {"abstract": data.get("AbstractText", ""), "answer": data.get("Answer", ""), "query": query}
            except Exception as e2:
                return {"error": f"Direct and proxy both failed: {e}; {e2}", "query": query}
        return {"error": str(e), "query": query}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DuckDuckGo search helper")
    parser.add_argument("--proxy", help="HTTP proxy URL", default=None)
    sub = parser.add_subparsers(dest="action")

    search_p = sub.add_parser("search", help="Web search")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--max", type=int, default=10, help="Max results")

    instant_p = sub.add_parser("instant", help="Instant answer")
    instant_p.add_argument("query", help="Search query")

    args = parser.parse_args()

    if args.action == "search":
        result = ddg_search(args.query, args.max, proxy=args.proxy)
    elif args.action == "instant":
        result = ddg_instant_answer(args.query, proxy=args.proxy)
    else:
        result = {"error": "Specify action: search or instant"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
