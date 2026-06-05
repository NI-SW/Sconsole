#!/usr/bin/env python3
"""Web page content extractor - extract clean text, links, images from URLs."""
import sys
import os
import json
import argparse
import urllib.request
import re
import socket
from html.parser import HTMLParser

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

class TextExtractor(HTMLParser):
    """Extract visible text from HTML, ignoring scripts, styles, etc."""
    
    SKIP_TAGS = {"script", "style", "noscript", "header", "footer", "nav", "aside"}
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []
        self.images = []
        self.current_tag = None
        self.skip_depth = 0
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        attrs_dict = dict(attrs)
        
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        
        if tag == "a" and "href" in attrs_dict:
            self.links.append(attrs_dict["href"])
        
        if tag == "img" and "src" in attrs_dict:
            self.images.append({
                "src": attrs_dict["src"],
                "alt": attrs_dict.get("alt", ""),
            })
        
        # Add line breaks for block elements
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text_parts.append("\n")
    
    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self.text_parts.append("\n")
    
    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)
    
    def get_text(self):
        return " ".join(self.text_parts).strip()

def extract_content(url, timeout=30, proxy=None, max_length=30000):
    """Fetch and extract clean content from a web page."""
    proxy = _resolve_proxy(proxy)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    handler = None
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    
    try:
        with opener.open(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            
            # Detect encoding
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[1].split(";")[0].strip()
            
            html = raw.decode(encoding, errors="replace")
    except Exception as e:
        return {"error": str(e), "url": url}
    
    # Extract title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    title = re.sub(r"<[^>]+>", "", title)
    
    # Extract meta description
    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    description = desc_match.group(1) if desc_match else ""
    
    # Extract text content
    extractor = TextExtractor()
    try:
        extractor.feed(html)
    except:
        pass
    text = extractor.get_text()
    
    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    
    # Filter links to only http(s)
    links = [l for l in extractor.links if l.startswith("http")]
    
    return {
        "url": url,
        "title": title,
        "description": description,
        "text": text[:max_length],
        "text_length": len(text),
        "links_count": len(links),
        "links": links[:30],
        "images_count": len(extractor.images),
        "images": extractor.images[:10],
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web page content extractor")
    parser.add_argument("url", help="URL to extract content from")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-length", type=int, default=30000)
    parser.add_argument("--proxy", help="HTTP proxy URL")
    
    args = parser.parse_args()
    result = extract_content(args.url, args.timeout, args.proxy, args.max_length)
    print(json.dumps(result, ensure_ascii=False, indent=2))
