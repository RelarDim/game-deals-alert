#!/usr/bin/env python3
"""Στέλνει mail για νέα άρθρα κατηγορίας Deals από το AllKeyShop blog."""
import json, os, smtplib, ssl, sys, urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from html import escape
from pathlib import Path

FEED = "https://www.allkeyshop.com/blog/feed/"
CATEGORY = "deals"
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
        })
    return items


def send(items):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("MAIL_TO", user)
    msg = EmailMessage()
    msg["Subject"] = f"🎮 {len(items)} νέα deals: {items[0]['title'][:60]}"
    msg["From"], msg["To"] = user, to
    msg.set_content("\n\n".join(f"{i['title']}\n{i['link']}" for i in items))
    rows = "".join(
        f"<li><a href='{escape(i['link'])}'>{escape(i['title'])}</a><br>"
        f"<small>{escape(i['date'])}</small></li>" for i in items)
    msg.add_alternative(f"<h3>Νέα deals από AllKeyShop</h3><ul>{rows}</ul>", subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)


def main():
    items = fetch_items()
    deals = [i for i in items if i["deal"]]
    if "--test" in sys.argv:
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
    SEEN.write_text(json.dumps(sorted(seen | {i["link"] for i in deals}), indent=1))


if __name__ == "__main__":
    main()
