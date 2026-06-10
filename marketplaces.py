import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import re
import random
import time
import json

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


def _random_headers(lang="en-US,en;q=0.9"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": lang,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }


def _fetch(url, params=None, retries=2, lang="en-US,en;q=0.9"):
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                url,
                headers=_random_headers(lang),
                params=params or {},
                timeout=12,
                allow_redirects=True,
            )
            r.raise_for_status()
            return r.text
        except Exception:
            if attempt < retries:
                time.sleep(1.5 ** attempt + random.uniform(0.1, 0.5))
    return ""


async def _async_fetch(session, url, params=None, lang="en-US,en;q=0.9", retries=2):
    for attempt in range(retries + 1):
        try:
            async with session.get(
                url,
                params=params or {},
                headers=_random_headers(lang),
                timeout=aiohttp.ClientTimeout(total=12),
                allow_redirects=True,
            ) as r:
                if r.status == 200:
                    return await r.text(errors="replace")
                return ""
        except Exception:
            if attempt < retries:
                await asyncio.sleep(1.5 ** attempt + random.uniform(0.1, 0.5))
    return ""


# ─── eBay (most scraper-friendly, reliable results) ───

def parse_ebay(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select(".s-item"):
        a = li.select_one(".s-item__link")
        if not a:
            continue
        title_el = li.select_one(".s-item__title")
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        if not title or title.lower() in ("shop on ebay", ""):
            continue
        href = a.get("href", "").split("?")[0]
        if not href:
            continue
        price_el = li.select_one(".s-item__price")
        price = price_el.get_text(strip=True) if price_el else None
        cond_el = li.select_one(".SECONDARY_INFO")
        cond = cond_el.get_text(strip=True) if cond_el else None
        items.append({"title": title, "url": href, "price": price, "condition": cond, "platform": "eBay"})
    return items[:10]


def fetch_ebay(query):
    html = _fetch("https://www.ebay.com/sch/i.html", params={"_nkw": query, "_sop": "12"})
    return parse_ebay(html)


async def async_fetch_ebay(session, query):
    html = await _async_fetch(session, "https://www.ebay.com/sch/i.html", params={"_nkw": query, "_sop": "12"})
    return parse_ebay(html)


# ─── Mercari JP (JavaScript SPA — extract embedded Next.js JSON if present) ───

def parse_mercari(html):
    if not html:
        return []
    items = []

    # Mercari JP embeds data in __NEXT_DATA__ script tag
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            pages = data.get("props", {}).get("pageProps", {})
            raw_items = (
                pages.get("initialSearchState", {}).get("items", [])
                or pages.get("items", [])
                or pages.get("searchResult", {}).get("items", [])
            )
            for item in raw_items[:10]:
                item_id = item.get("id") or item.get("itemId")
                name = item.get("name") or item.get("title", "")
                price = item.get("price") or item.get("buyerPaymentAmount")
                if item_id and name:
                    items.append({
                        "title": name,
                        "url": f"https://jp.mercari.com/item/{item_id}",
                        "price": f"¥{price:,}" if isinstance(price, int) else (f"¥{price}" if price else None),
                        "platform": "Mercari JP",
                    })
        except Exception:
            pass

    if not items:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True)[:60]:
            href = a["href"]
            text = a.get_text(strip=True)
            if text and re.search(r"/(items?|m\d{10})", href):
                url = href if href.startswith("http") else f"https://jp.mercari.com{href}"
                items.append({"title": text, "url": url, "price": None, "platform": "Mercari JP"})

    return items[:8]


def fetch_mercari(query):
    html = _fetch("https://jp.mercari.com/search", params={"keyword": query}, lang="ja,en-US;q=0.7,en;q=0.3")
    return parse_mercari(html)


async def async_fetch_mercari(session, query):
    html = await _async_fetch(session, "https://jp.mercari.com/search", params={"keyword": query}, lang="ja,en-US;q=0.7,en;q=0.3")
    return parse_mercari(html)


# ─── Yahoo Auctions JP ───

def parse_yahoo(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for card in soup.select(".Product") or soup.select("li.Product"):
        a = card.select_one("a.Product__imageLink") or card.select_one("a[href*='page.auctions.yahoo']") or card.select_one("a[href*='/jp/auction/']")
        if not a:
            continue
        href = a.get("href", "")
        title_el = card.select_one(".Product__title") or card.select_one("h3") or card.select_one(".title")
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        price_el = card.select_one(".Product__priceValue") or card.select_one(".u-txt-attention") or card.select_one(".price")
        price = price_el.get_text(strip=True) if price_el else None
        if href and title:
            items.append({"title": title, "url": href, "price": price, "platform": "Yahoo Auctions"})

    if not items:
        for a in soup.find_all("a", href=True)[:80]:
            href = a["href"]
            text = a.get_text(strip=True)
            if text and ("page.auctions.yahoo.co.jp/jp/auction" in href or "/jp/auction/" in href):
                items.append({"title": text, "url": href, "price": None, "platform": "Yahoo Auctions"})

    return items[:8]


def fetch_yahoo(query):
    import urllib.parse
    html = _fetch(
        "https://auctions.yahoo.co.jp/search/search",
        params={"p": query, "ei": "UTF-8", "auccat": ""},
        lang="ja,en-US;q=0.7,en;q=0.3",
    )
    return parse_yahoo(html)


async def async_fetch_yahoo(session, query):
    html = await _async_fetch(
        session,
        "https://auctions.yahoo.co.jp/search/search",
        params={"p": query, "ei": "UTF-8", "auccat": ""},
        lang="ja,en-US;q=0.7,en;q=0.3",
    )
    return parse_yahoo(html)


# ─── Vinted ───

def parse_vinted(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for card in soup.select("[data-testid='grid-item']") or soup.select(".feed-grid__item"):
        a = card.select_one("a[href*='/items/']")
        if not a:
            continue
        href = a.get("href", "")
        title_el = card.select_one(".ItemBox_title__Hye3l") or card.select_one("[class*='title']")
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        price_el = card.select_one("[class*='price']")
        price = price_el.get_text(strip=True) if price_el else None
        url = href if href.startswith("http") else f"https://www.vinted.com{href}"
        if title:
            items.append({"title": title, "url": url, "price": price, "platform": "Vinted"})

    if not items:
        for a in soup.find_all("a", href=True)[:60]:
            href = a["href"]
            text = a.get_text(strip=True)
            if text and "/items/" in href:
                url = href if href.startswith("http") else f"https://www.vinted.com{href}"
                items.append({"title": text, "url": url, "price": None, "platform": "Vinted"})

    return items[:8]


def fetch_vinted(query):
    html = _fetch("https://www.vinted.com/catalog", params={"search_text": query})
    return parse_vinted(html)


async def async_fetch_vinted(session, query):
    html = await _async_fetch(session, "https://www.vinted.com/catalog", params={"search_text": query})
    return parse_vinted(html)


# ─── Grailed (Cloudflare protected — link-only fallback) ───

def parse_grailed(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True)[:60]:
        href = a["href"]
        text = a.get_text(strip=True)
        if text and "/listings/" in href and len(text) > 5:
            url = href if href.startswith("http") else f"https://www.grailed.com{href}"
            items.append({"title": text, "url": url, "price": None, "platform": "Grailed"})
    return items[:8]


def fetch_grailed(query):
    html = _fetch("https://www.grailed.com/listings/search", params={"search_query": query})
    return parse_grailed(html)


async def async_fetch_grailed(session, query):
    html = await _async_fetch(session, "https://www.grailed.com/listings/search", params={"search_query": query})
    return parse_grailed(html)


# ─── Xianyu (requires app login — generate correct link for manual search) ───
# Xianyu is app-only and login-gated; we generate the correct deep link URL.

def fetch_xianyu(query):
    import urllib.parse
    q = urllib.parse.quote(query)
    return [{
        "title": f"Search Xianyu: {query}",
        "url": f"https://www.goofish.com/search?keyword={q}",
        "price": None,
        "platform": "Xianyu",
    }]


async def async_fetch_xianyu(session, query):
    return fetch_xianyu(query)


# ─── Taobao (login-gated JS SPA — generate search link) ───

def parse_taobao(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True)[:80]:
        href = a["href"]
        text = a.get_text(strip=True)
        if text and ("item.htm" in href or "detail.tmall.com" in href):
            url = href if href.startswith("http") else f"https://item.taobao.com{href}"
            items.append({"title": text, "url": url, "price": None, "platform": "Taobao"})
    return items[:8]


def fetch_taobao(query):
    import urllib.parse
    html = _fetch(f"https://s.taobao.com/search", params={"q": query}, lang="zh-CN,zh;q=0.9,en;q=0.3")
    return parse_taobao(html)


async def async_fetch_taobao(session, query):
    html = await _async_fetch(session, "https://s.taobao.com/search", params={"q": query}, lang="zh-CN,zh;q=0.9,en;q=0.3")
    return parse_taobao(html)


# ─── Weidian (JS SPA — generate search link) ───

def parse_weidian(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True)[:80]:
        href = a["href"]
        text = a.get_text(strip=True)
        if text and ("weidian.com" in href or "/item" in href):
            url = href if href.startswith("http") else f"https://weidian.com{href}"
            items.append({"title": text, "url": url, "price": None, "platform": "Weidian"})
    return items[:8]


def fetch_weidian(query):
    import urllib.parse
    html = _fetch(f"https://weidian.com/", params={"search": query})
    return parse_weidian(html)


async def async_fetch_weidian(session, query):
    html = await _async_fetch(session, "https://weidian.com/", params={"search": query})
    return parse_weidian(html)


# ─── Async concurrent search ───

async def async_search_all_marketplaces(query):
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            async_fetch_ebay(session, query),
            async_fetch_mercari(session, query),
            async_fetch_yahoo(session, query),
            async_fetch_vinted(session, query),
            async_fetch_grailed(session, query),
            async_fetch_taobao(session, query),
            async_fetch_weidian(session, query),
            async_fetch_xianyu(session, query),
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for r in all_results:
        if isinstance(r, list):
            results.extend(r)

    seen = set()
    out = []
    for r in results:
        url = r.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(r)
    return out[:15]


def search_all_marketplaces(query):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Called from inside async context — use sequential sync fallback
            return _sync_search_sequential(query)
        return loop.run_until_complete(async_search_all_marketplaces(query))
    except RuntimeError:
        return _sync_search_sequential(query)
    except Exception:
        return []


def _sync_search_sequential(query):
    results = []
    for fn in [fetch_ebay, fetch_mercari, fetch_yahoo, fetch_vinted, fetch_grailed]:
        try:
            results.extend(fn(query))
        except Exception:
            pass
    seen = set()
    out = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            out.append(r)
    return out[:12]
