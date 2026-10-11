#!/usr/bin/env python3
"""Μαζεύει εκπτώσεις PC από Steam, GOG, CheapShark (Epic, Humble, Fanatical κ.ά.)
και δωρεάν παιχνίδια από GamerPower, και τα γράφει σε deals.json (τιμές σε EUR)."""
import html as htmllib, json, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).with_name("deals.json")
UA = "Mozilla/5.0 (compatible; PersonalDealsPage/1.0; hobby project)"


def get(url, as_json=True, tries=4):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read().decode("utf8", "replace")
            return json.loads(body) if as_json else body
        except Exception as e:  # 429 / 5xx / timeout: περιμένουμε και ξαναδοκιμάζουμε
            last = e
            print(f"  retry {attempt + 1}/{tries} {url[:80]} -> {e!r}")
            time.sleep(3 * (attempt + 1))
    raise last


def safe(fn, name):
    try:
        out = fn()
        print(f"{name}: {len(out)}")
        return out
    except Exception as e:  # μία πηγή που πέφτει δεν πρέπει να χαλάει τις άλλες
        print(f"{name}: FAILED {e!r}")
        return []


def eur(text):
    """'24,99€' / '4,55 €' -> 24.99"""
    m = re.search(r"(\d[\d.]*(?:,\d+)?)", text.replace("\xa0", " "))
    return float(m.group(1).replace(".", "").replace(",", ".")) if m else None


def steam():
    out = []
    for page in range(5):
        d = get("https://store.steampowered.com/search/results/?query&start=%d&count=100"
                "&specials=1&cc=gr&l=english&infinite=1&json=1&category1=998&sort_by=_ASC" % (page * 100))
        for m in re.finditer(r'<a href="(https://store\.steampowered\.com/(?:app|sub)/(\d+)/[^"?]*)[^>]*>(.*?)</a>',
                             d["results_html"], re.S):
            url, appid, body = m.groups()
            title = re.search(r'class="title">(.*?)</span>', body, re.S)
            disc = re.search(r'data-discount="(\d+)"', body)
            final = re.search(r'data-price-final="(\d+)"', body)
            if not (title and disc and final) or int(disc.group(1)) == 0:
                continue
            orig = re.search(r'discount_original_price">(.*?)<', body)
            rev = re.search(r"(\d+)% of the ([\d,]+) user reviews", body)
            img = re.search(r'<img src="([^"]+)"', body)
            out.append({
                "title": htmllib.unescape(title.group(1).strip()), "store": "Steam", "url": url,
                "img": img.group(1) if img else "", "disc": int(disc.group(1)),
                "price": int(final.group(1)) / 100, "orig": eur(orig.group(1)) if orig else None,
                "rating": int(rev.group(1)) if rev else None,
                "reviews": int(rev.group(2).replace(",", "")) if rev else 0,
            })
        time.sleep(1)
    return out


def gog():
    out = []
    for page in range(1, 9):
        d = get("https://catalog.gog.com/v1/catalog?limit=48&order=desc:trending&discounted=eq:true"
                "&productType=in:game,pack&currencyCode=EUR&countryCode=GR&locale=en-US&page=%d" % page)
        for p in d["products"]:
            pr = p["price"]
            disc = int(re.sub(r"\D", "", pr.get("discount") or "0") or 0)
            if not disc:
                continue
            rating = p.get("reviewsRating")
            out.append({
                "title": p["title"], "store": "GOG", "url": p["storeLink"],
                "img": p.get("coverHorizontal", ""), "disc": disc,
                "price": float(pr["finalMoney"]["amount"]), "orig": float(pr["baseMoney"]["amount"]),
                "rating": round(rating * 2) if rating else None, "reviews": 0,
            })
        time.sleep(0.5)
    return out


def cheapshark(usd_eur):
    all_stores = get("https://www.cheapshark.com/api/1.0/stores")
    stores = {s["storeID"]: s["storeName"] for s in all_stores}
    # Steam και GOG τα παίρνουμε απευθείας σε EUR. Τα υπόλοιπα ένα-ένα, ώστε
    # και τα μικρά καταστήματα να έχουν δική τους κάλυψη.
    ids = [s["storeID"] for s in all_stores if s["isActive"] and s["storeName"] not in ("Steam", "GOG")]
    out = []
    for sid in ids:
      try:
        for page in range(4):
            rows = get("https://www.cheapshark.com/api/1.0/deals?onSale=1&sortBy=Savings&storeID=%s"
                       "&pageSize=60&pageNumber=%d" % (sid, page))
            for d in rows:
                if float(d["savings"]) < 1:
                    continue
                cnt = int(d["steamRatingCount"] or 0)
                out.append({
                    "title": htmllib.unescape(d["title"]), "store": stores.get(d["storeID"], "?"),
                    "url": "https://www.cheapshark.com/redirect?dealID=" + urllib.parse.quote(d["dealID"]),
                    "img": d["thumb"], "disc": round(float(d["savings"])),
                    "price": round(float(d["salePrice"]) * usd_eur, 2),
                    "orig": round(float(d["normalPrice"]) * usd_eur, 2),
                    "rating": int(d["steamRatingPercent"]) if cnt else None, "reviews": cnt,
                })
            if len(rows) < 60:
                break
            time.sleep(1)
      except Exception as e:
        print(f"cheapshark store {sid} skipped: {e!r}")
      time.sleep(1)
    return out


def free_games(usd_eur):
    out = []
    for g in get("https://www.gamerpower.com/api/giveaways?platform=pc&type=game"):
        worth = re.sub(r"[^\d.]", "", g.get("worth") or "")
        out.append({
            "title": re.sub(r"\s*\((?:[^)]*)\)\s*Giveaway$", "", g["title"]).strip(),
            "store": g.get("platforms", "").split(",")[0].strip() or "PC",
            "url": g["open_giveaway_url"], "img": g.get("thumbnail", ""),
            "worth": round(float(worth) * usd_eur, 2) if worth else None,
            "ends": g.get("end_date") if g.get("end_date") not in (None, "N/A") else None,
        })
    return out


def main():
    rate = get("https://api.frankfurter.app/latest?from=USD&to=EUR")["rates"]["EUR"]
    deals = safe(steam, "steam") + safe(gog, "gog") + safe(lambda: cheapshark(rate), "cheapshark")
    free = safe(lambda: free_games(rate), "free")
    try:
        old = json.loads(OUT.read_text())
    except Exception:
        old = {"deals": [], "free": []}
    have = {d["store"] for d in deals}
    for name in ("Steam", "GOG"):
        if name not in have:
            print(f"{name} missing, keeping previous data")
            deals += [d for d in old["deals"] if d["store"] == name]
    if not any(d["store"] not in ("Steam", "GOG") for d in deals):
        print("cheapshark stores missing, keeping previous data")
        deals += [d for d in old["deals"] if d["store"] not in ("Steam", "GOG")]
    else:  # κρατάμε και κάθε μεμονωμένο κατάστημα του CheapShark που έλειψε αυτή τη φορά
        have = {d["store"] for d in deals}
        deals += [d for d in old["deals"] if d["store"] not in have]
    if not free:
        free = old.get("free", [])
    if not deals:  # αν όλα απέτυχαν, κρατάμε το προηγούμενο αρχείο
        raise SystemExit("no deals fetched, keeping old file")
    OUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "usd_eur": rate, "deals": deals, "free": free,
    }, ensure_ascii=False, separators=(",", ":")))
    print("written", len(deals), "deals,", len(free), "free")


if __name__ == "__main__":
    main()
