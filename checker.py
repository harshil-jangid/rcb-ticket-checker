"""
RCB Ticket Availability Checker
- Scrapes shop.royalchallengers.com/ticket using Playwright (JS-rendered page)
- Checks for configured match keywords (e.g. "Chennai", "CSK")
- Notifies via Telegram when tickets go live
"""

import os
import re
import json
import asyncio
import hashlib
import httpx
from datetime import datetime
from playwright.async_api import async_playwright

# ─── CONFIG ──────────────────────────────────────────────────────────────────

TARGET_URL = "https://shop.royalchallengers.com/ticket"

# Match keywords to watch for (case-insensitive). Notifies if ANY match is found.
# Set to [] to alert for ALL matches going live.
WATCH_MATCHES = [
    "Chennai",
    "CSK",
    # "Mumbai",   # uncomment to also watch RCB vs MI
    # "Kolkata",
]

# Telegram config — set via env vars or hardcode here for local testing
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# State file to avoid repeat notifications for the same matches
STATE_FILE = "/tmp/rcb_seen_matches.json"

# ─── SCRAPER ─────────────────────────────────────────────────────────────────

async def fetch_ticket_page() -> list[dict]:
    """
    Launches a headless Chromium browser, loads the RCB ticket page,
    waits for JS to render, and extracts all visible match/ticket cards.
    Returns a list of dicts: { title, url, available }
    """
    matches_found = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        # Spoof a real user-agent so the site doesn't block headless browsers
        await page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        })

        print(f"[{now()}] Loading {TARGET_URL} ...")
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=30_000)

        # Give JS-heavy frameworks an extra moment to settle
        await page.wait_for_timeout(3000)

        # Dump the full rendered text for debugging if needed
        page_text = await page.inner_text("body")

        # ── Strategy 1: find <a> tags that look like ticket/match links ──────
        links = await page.query_selector_all("a[href]")
        for link in links:
            href  = await link.get_attribute("href") or ""
            label = (await link.inner_text()).strip()
            label = re.sub(r"\s+", " ", label)  # collapse whitespace

            if not label or len(label) < 4:
                continue
            if not any(kw in label.lower() for kw in [
                "vs", "rcb", "royal challengers", "ticket", "match"
            ]):
                continue

            # Detect if the link/button is disabled / sold-out / coming-soon
            class_attr = (await link.get_attribute("class") or "").lower()
            aria_label  = (await link.get_attribute("aria-label") or "").lower()
            combined    = f"{label.lower()} {class_attr} {aria_label}"

            is_sold_out    = any(w in combined for w in ["sold out", "soldout", "coming soon", "notify me", "disabled", "unavailable"])
            is_available   = not is_sold_out

            full_url = href if href.startswith("http") else f"https://shop.royalchallengers.com{href}"

            matches_found.append({
                "title":     label,
                "url":       full_url,
                "available": is_available,
                "raw":       combined[:120],
            })

        # ── Strategy 2: fallback — scan raw text blocks for match info ───────
        if not matches_found:
            print(f"[{now()}] No link-based cards found, falling back to text scan...")
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            for i, line in enumerate(lines):
                if re.search(r"vs\.?\s+\w+|match\s*\d+|IPL\s+\d{4}", line, re.IGNORECASE):
                    snippet = " | ".join(lines[max(0,i-1):i+3])
                    matches_found.append({
                        "title":     line,
                        "url":       TARGET_URL,
                        "available": True,   # assume available if shown
                        "raw":       snippet[:200],
                    })

        await browser.close()

    return matches_found


# ─── FILTER ──────────────────────────────────────────────────────────────────

def filter_target_matches(matches: list[dict]) -> list[dict]:
    """
    From all scraped matches, return only the ones that:
      1. Are available (not sold-out / coming-soon)
      2. Match any keyword in WATCH_MATCHES (or all, if WATCH_MATCHES is empty)
    """
    results = []
    for m in matches:
        if not m["available"]:
            continue
        if not WATCH_MATCHES:
            results.append(m)
            continue
        for kw in WATCH_MATCHES:
            if kw.lower() in m["title"].lower():
                results.append(m)
                break
    return results


# ─── STATE TRACKING (avoid duplicate notifications) ──────────────────────────

def load_seen() -> set:
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def match_id(m: dict) -> str:
    return hashlib.md5(m["title"].encode()).hexdigest()


# ─── TELEGRAM NOTIFICATION ───────────────────────────────────────────────────

async def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram not configured — printing notification only:")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "Markdown",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[{now()}] ✅ Telegram notification sent.")
        else:
            print(f"[{now()}] ❌ Telegram error: {resp.text}")


def build_message(new_matches: list[dict]) -> str:
    lines = [
        "🏏 *RCB Ticket Alert!* Tickets are now LIVE!\n",
        f"🔗 {TARGET_URL}\n",
    ]
    for m in new_matches:
        status = "✅ Available" if m["available"] else "❌ Sold Out"
        lines.append(f"• *{m['title']}* — {status}")
        if m["url"] != TARGET_URL:
            lines.append(f"  👉 {m['url']}")
    lines.append(f"\n_Checked at {now()}_")
    return "\n".join(lines)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def main():
    print(f"[{now()}] 🔍 Checking RCB tickets...")
    print(f"[{now()}] Watching for: {WATCH_MATCHES or 'ALL matches'}")

    all_matches     = await fetch_ticket_page()
    target_matches  = filter_target_matches(all_matches)

    print(f"[{now()}] Found {len(all_matches)} total listings, {len(target_matches)} matched your filter.")

    if not target_matches:
        print(f"[{now()}] No matching available tickets found. Will check again next run.")
        return

    # Only notify for matches we haven't seen before
    seen       = load_seen()
    new_ones   = [m for m in target_matches if match_id(m) not in seen]

    if not new_ones:
        print(f"[{now()}] Matches found but already notified. No new alert needed.")
        return

    # Send notification
    msg = build_message(new_ones)
    await send_telegram(msg)

    # Mark as seen
    for m in new_ones:
        seen.add(match_id(m))
    save_seen(seen)


if __name__ == "__main__":
    asyncio.run(main())
