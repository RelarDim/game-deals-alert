#!/usr/bin/env python3
"""Στέλνει mail για νέα άρθρα κατηγορίας Deals από το AllKeyShop blog."""
import json, os, re, smtplib, ssl, sys, urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from html import escape
from pathlib import Path

FEED = "https://www.allkeyshop.com/blog/feed/"
CATEGORY = "deals"  # σύγκριση χωρίς διάκριση πεζών/κεφαλαίων
PC_RE = re.compile(r"\bpc\b|\bsteam\b", re.I)
PRICE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*€|[$£€]\s*(\d+(?:[.,]\d+)?)")
PCT_RE = re.compile(r"(\d{1,2})\s*%")
SEEN = Path(__file__).with_name("seen.json")


def fetch_items():
    req = urllib.request.Request(FEED, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        cats = [(c.text or "").strip().lower() for c in it.findall("category")]
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "date": (it.findtext("pubDate") or "").strip(),
            "deal": CATEGORY in cats,
            "pc": bool(PC_RE.search(" ".join(cats) + " " + (it.findtext("title") or "")
                                    + " " + (it.findtext("description") or ""))),
        })
    return items


def price_info(url):
    """Βγάζει τις γραμμές με τιμές από τα Key Takeaways και μια εκτίμηση έκπτωσης."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf8", "replace")
    except Exception:
        return [], None
    box = re.search(r'class="aks-takeaways".*?</ul>', html, re.S)
    bullets = re.findall(r"<span>(.*?)</span>", box.group(0), re.S) if box else []
    bullets = [re.sub(r"<[^>]+>", "", b).replace("&quot;", '"').replace("&#39;", "'")
               .replace("&amp;", "&").strip() for b in bullets]
    lines = [b for b in bullets if PRICE_RE.search(b) or PCT_RE.search(b)]
    discount = None
    for b in lines:
        m = PCT_RE.search(b)
        if m:
            discount = f"-{m.group(1)}%"
            break
        nums = [float((a or c).replace(",", ".")) for a, c in PRICE_RE.findall(b)]
        if len(nums) >= 2 and min(nums) < max(nums):
            discount = f"~-{round((1 - min(nums) / max(nums)) * 100)}% (εκτίμηση)"
            break
    return lines, discount


def send(items):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO", user)
    msg = EmailMessage()
    msg["Subject"] = f"🎮 {len(items)} νέα deals: {items[0]['title'][:60]}"
    msg["From"], msg["To"] = user, to
    for i in items:
        i["lines"], i["disc"] = price_info(i["link"])
    msg.set_content("\n\n".join(
        f"{i['title']}" + (f"  [{i['disc']}]" if i["disc"] else "")
        + "\n" + "\n".join(i["lines"]) + f"\n{i['link']}" for i in items))
    rows = "".join(
        f"<li><a href='{escape(i['link'])}'>{escape(i['title'])}</a>"
        + (f" <b style='color:#1a7f37'>{escape(i['disc'])}</b>" if i["disc"] else "")
        + "".join(f"<br><small>{escape(l)}</small>" for l in i["lines"])
        + f"<br><small style='color:#888'>{escape(i['date'])}</small><br><br></li>"
        for i in items)
    msg.add_alternative(f"<h3>Νέα deals από AllKeyShop</h3><ul>{rows}</ul>", subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)


def main():
    items = fetch_items()
    deals = [i for i in items if i["deal"] and i["pc"]]
    if "--test" in sys.argv:  # στέλνει τα τρέχοντα deals χωρίς να αγγίξει το state
        send(deals or items[:3])
        print("Test mail sent")
        return
    first_run = not SEEN.exists()
    seen = set(json.loads(SEEN.read_text())) if not first_run else set()
    new = [i for i in deals if i["link"] not in seen]
    if new and not first_run:
        send(new)
        print(f"Sent {len(new)} new deals")
    else:
        print("First run, seeding" if first_run else "No new deals")
    # κρατάμε και παλιά links ώστε να μη στείλει ξανά άρθρο που βγήκε από το feed
    SEEN.write_text(json.dumps(sorted(seen | {i["link"] for i in deals}), indent=1))


if __name__ == "__main__":
    main()
