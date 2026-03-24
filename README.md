# 🏏 RCB Ticket Checker

Polls `shop.royalchallengers.com/ticket` every 5 minutes and sends you a **Telegram notification** the moment tickets for your configured match go live.

Runs free on **GitHub Actions** — no server, no phone, no laptop needed.

---

## Setup (15 minutes, one-time)

### Step 1 — Create your Telegram Bot

1. Open Telegram → search **@BotFather** → tap Start
2. Send `/newbot`, give it a name and username
3. BotFather replies with your **Bot Token** → copy it  
   (looks like: `7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxx`)
4. Open your new bot in Telegram → tap **Start** (so it can message you)
5. Get your Chat ID — visit this URL in your browser (replace YOUR_TOKEN):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
   Send any message to your bot first, then refresh — you'll see `"id": 123456789` in the JSON under `message.chat`. That's your **Chat ID**.

---

### Step 2 — Fork & configure this repo

1. **Fork** this repo to your GitHub account
2. Go to your fork → **Settings → Secrets and variables → Actions**
3. Add two **Repository secrets**:
   | Secret Name | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | Your bot token from Step 1 |
   | `TELEGRAM_CHAT_ID` | Your numeric chat ID from Step 1 |

---

### Step 3 — Configure your match

In `checker.py`, edit the `WATCH_MATCHES` list:

```python
# Watch only these matches:
WATCH_MATCHES = [
    "Chennai",   # RCB vs CSK
    "CSK",
]

# To get alerts for ALL matches:
WATCH_MATCHES = []
```

Commit the change — the workflow picks it up automatically.

---

### Step 4 — Enable GitHub Actions

1. Go to your fork → **Actions tab**
2. Click **"I understand my workflows, go ahead and enable them"**
3. The workflow will now run every 5 minutes automatically

To test immediately: Actions tab → **RCB Ticket Checker** → **Run workflow**

---

## How it works

```
GitHub Actions (every 5 min)
        ↓
  checker.py
        ↓
  Playwright (headless Chromium)
        ↓
  Loads shop.royalchallengers.com/ticket
  (renders full JS like a real browser)
        ↓
  Extracts match listings + availability
        ↓
  Filters by WATCH_MATCHES keywords
        ↓
  New match found? → Telegram notification → iPhone 🎉
  Already notified? → Skip (no spam)
  Nothing found? → Silent, retry in 5 mins
```

---

## FAQ

**Why Playwright and not just requests?**  
The RCB site is a React/JS app — the HTML is empty on first load. Playwright runs a real headless browser so the JS executes and the ticket cards render.

**GitHub Actions is free?**  
Yes. Free accounts get 2,000 minutes/month. This job takes ~60s per run × 288 runs/day = ~288 min/day = ~8,640 min/month — which exceeds the free tier for **private repos**. Make your repo **public** and Actions are unlimited. If you want it private, upgrade to a paid plan or reduce polling frequency.

**Can I run it locally?**  
```bash
pip install playwright httpx
playwright install chromium
export TELEGRAM_BOT_TOKEN=your_token
export TELEGRAM_CHAT_ID=your_chat_id
python checker.py
```

**The selectors aren't working / no matches found**  
The RCB site may update its HTML structure. Run locally and check the debug output. You may need to tweak the CSS selectors or keyword matching in `fetch_ticket_page()`. Open an issue with the page HTML and I can help fix it.

---

## Notification sample

```
🏏 RCB Ticket Alert! Tickets are now LIVE!

🔗 https://shop.royalchallengers.com/ticket

• RCB vs Chennai Super Kings — ✅ Available
  👉 https://shop.royalchallengers.com/ticket/rcb-vs-csk-2025

Checked at 2025-03-24 14:35:02
```
