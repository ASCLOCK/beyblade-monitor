#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爆旋陀螺（Beyblade）香港網店新貨監測 + Telegram 通知

監測以下四間香港網店：
  1. Last Chance Toy   (Shopify)
  2. T Club            (Shopify)
  3. Toys"R"Us 香港    (Salesforce Demandware，經產品 sitemap)
  4. Hobbyland 玩具模型倉 (自家 API)

偵測兩類事件：
  - 新上架：之前未見過的商品 ID 出現
  - 補貨：  之前缺貨/不可訂購的商品變成可訂購

只使用 Python 標準函式庫（urllib/json），無需 pip 安裝任何套件。

用法：
  python monitor.py              # 執行一次（掃描 + 偵測 + 通知 + 儲存狀態）
  python monitor.py --scan       # 只掃描並列出目前符合關鍵字的商品，不通知、不改狀態
  python monitor.py --loop 30    # 每 30 分鐘自動執行一次（常駐）
  python monitor.py --test       # 送一封測試訊息到 Telegram，確認設定正確
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "config.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 基本 HTTP 工具
# ---------------------------------------------------------------------------

def http_text(url, timeout=60, headers=None, method=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_json(url, timeout=60, headers=None):
    return json.loads(http_text(url, timeout=timeout, headers=headers))


def http_post_json(url, payload, timeout=60, headers=None):
    h = {"User-Agent": UA, "Content-Type": "application/json",
         "Accept": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---------------------------------------------------------------------------
# Telegram 通知
# ---------------------------------------------------------------------------

def telegram_send_message(bot_token, chat_id, text):
    """送純文字訊息，回傳 True/False。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "false",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8", "replace"))
    return bool(resp.get("ok"))


def telegram_send_photo(bot_token, chat_id, photo_url, caption):
    """送圖片 + 說明文字。失敗時回傳 False（呼叫端會退回純文字）。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=40) as r:
        resp = json.loads(r.read().decode("utf-8", "replace"))
    return bool(resp.get("ok"))


def resolve_telegram(cfg):
    """優先讀環境變數（GitHub Secrets），其次讀 config.json。回傳 (token, chat_id)。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or \
        (cfg.get("telegram") or {}).get("bot_token") or ""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or \
        (cfg.get("telegram") or {}).get("chat_id") or ""
    return token.strip(), str(chat_id).strip()


def notify_item(bot_token, chat_id, kind, shop_name, item):
    """根據事件種類（new/restock）組裝並送出通知。"""
    if kind == "new":
        head = "🆕 新貨上架"
    elif kind == "restock":
        head = "🔄 補貨／重新可訂購"
    else:
        head = "ℹ️ 更新"

    lines = [f"{head}｜{shop_name}", ""]
    title = (item.get("title") or "").strip()
    if title:
        lines.append(title)
    price = item.get("price")
    if price not in (None, ""):
        lines.append(f"💰 價格：HKD {price}")
    status = item.get("status")
    if status:
        lines.append(f"📦 狀態：{status}")
    url = item.get("url")
    if url:
        lines.append(f"🔗 {url}")

    text = "\n".join(lines)
    image = item.get("image")
    if image:
        try:
            if telegram_send_photo(bot_token, chat_id, image, text):
                return True
            # 圖片失敗就退回純文字
        except Exception:
            pass
    try:
        return telegram_send_message(bot_token, chat_id, text)
    except Exception as e:
        log(f"Telegram 發送失敗：{e}")
        return False


# ---------------------------------------------------------------------------
# 各網店擷取器：回傳 list[dict]
# 每個 item 欄位：id, title, url, price, orderable, image, status
#   orderable: True=可訂購, False=缺貨/不可訂購, None=未知
# ---------------------------------------------------------------------------

def scrape_shopify(shop_cfg, kw_re, exclude_re):
    base = shop_cfg["url"].rstrip("/")
    items = []
    page = 1
    while True:
        data = http_json(f"{base}/products.json?limit=250&page={page}")
        products = data.get("products") or []
        if not products:
            break
        for p in products:
            title = p.get("title") or ""
            if not matches(kw_re, exclude_re, title):
                continue
            variants = p.get("variants") or []
            orderable = any(v.get("available") for v in variants)
            price = variants[0].get("price") if variants else None
            images = p.get("images") or []
            image = images[0].get("src") if images else None
            items.append({
                "id": str(p.get("id")),
                "title": title,
                "url": f"{base}/products/{p.get('handle')}",
                "price": price,
                "orderable": orderable,
                "image": image,
                "status": "有貨" if orderable else "缺貨／預訂",
            })
        page += 1
        if page > 100:
            break
    return items


def scrape_toysrus(shop_cfg, kw_re, exclude_re):
    sitemap = shop_cfg["sitemap"]
    xml = http_text(sitemap, timeout=120)
    items = []
    seen = set()
    # 逐個 <url> 區塊解析 loc + lastmod
    for m in re.finditer(
            r"<url>\s*<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>",
            xml, re.S):
        loc = m.group(1)
        # 跳過英文重複頁，只保留 zh-hk
        if "/en-hk/" in loc:
            continue
        if not matches(kw_re, exclude_re, loc):
            continue
        idm = re.search(r"-(\d+)\.html$", loc)
        if not idm:
            continue
        pid = idm.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        # 從網址 slug 重建可讀標題（去掉尾端商品編號）
        slug = loc.rsplit("/", 2)[-1]
        slug = slug[:-5] if slug.endswith(".html") else slug
        slug = re.sub(rf"-{re.escape(pid)}$", "", slug)
        title = re.sub(r"[_\-]+", " ", slug).strip()
        items.append({
            "id": pid,
            "title": title,
            "url": loc,
            "price": None,
            "orderable": None,      # sitemap 無庫存資訊，只偵測「新上架」
            "image": None,
            "status": None,
            "lastmod": m.group(2),
        })
    return items


def scrape_hobbyland(shop_cfg, kw_re, exclude_re):
    backend = shop_cfg["backend"].rstrip("/")
    frontend = shop_cfg["url"].rstrip("/")
    static = shop_cfg["static"].rstrip("/")
    search_terms = shop_cfg.get("search_terms") or ["陀螺"]
    collected = {}
    for term in search_terms:
        page = 1
        while True:
            data = http_post_json(
                f"{backend}/api/products", {"page": page, "search": term})
            d = data.get("data") or {}
            lst = d.get("list") or []
            total_pages = d.get("total_pages") or 1
            for it in lst:
                title = it.get("title") or ""
                if not matches(kw_re, exclude_re, title):
                    continue
                sku = str(it.get("sku") or it.get("link") or it.get("title"))
                link = it.get("link") or ""
                url = link if link.startswith("http") else frontend + link
                pic = it.get("pic1")
                image = (static + "/" + pic) if pic else None
                sell_type = it.get("sell_type") or ""
                stock = it.get("stock")
                blocked = bool(it.get("is_block"))
                # 可訂購 = 未被封鎖；有庫存或標記為現貨/預訂皆算可訂購
                orderable = (not blocked) and (
                    (stock is not None and stock > 0)
                    or sell_type in ("現貨", "預訂")
                    or "現貨" in sell_type or "預訂" in sell_type
                )
                collected[sku] = {
                    "id": sku,
                    "title": title,
                    "url": url,
                    "price": it.get("price"),
                    "orderable": orderable,
                    "image": image,
                    "status": sell_type or ("有貨" if orderable else "缺貨"),
                }
            if page >= total_pages:
                break
            page += 1
            if page > 50:
                break
    return list(collected.values())


SCRAPERS = {
    "shopify": scrape_shopify,
    "toysrus": scrape_toysrus,
    "hobbyland": scrape_hobbyland,
}


def scrape_shop(shop_key, shop_cfg, cfg, kw_re, exclude_re):
    scraper = SCRAPERS.get(shop_cfg["type"])
    if scraper is None:
        raise ValueError(f"未知網店類型: {shop_cfg['type']}")
    items = scraper(shop_cfg, kw_re, exclude_re)
    log(f"[{shop_key}] 掃到 {len(items)} 件符合關鍵字的商品")
    return items


# ---------------------------------------------------------------------------
# 狀態（偵測新貨 / 補貨）
# ---------------------------------------------------------------------------

def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log(f"狀態檔 {path} 無法讀取，將重新建立")
    return {"shops": {}}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def detect_events(cfg, state, kw_re, exclude_re):
    """回傳 (events, new_shops)。events = list[(kind, shop_key, item)]。"""
    events = []
    new_shops = []
    for shop_key, shop_cfg in cfg["shops"].items():
        if not shop_cfg.get("enabled", True):
            continue
        try:
            items = scrape_shop(shop_key, shop_cfg, cfg, kw_re, exclude_re)
        except Exception as e:
            log(f"[{shop_key}] 掃描失敗：{e}")
            continue
        time.sleep(cfg.get("request_interval_seconds", 0.4))

        prev = state["shops"].get(shop_key)
        new_state = {}
        if prev is None:
            new_shops.append((shop_key, len(items)))
            for it in items:
                new_state[it["id"]] = {
                    "orderable": it["orderable"],
                    "title": it["title"],
                }
        else:
            for it in items:
                oid = it["id"]
                prev_item = prev.get(oid)
                if prev_item is None:
                    events.append(("new", shop_key, it))
                else:
                    prev_ok = prev_item.get("orderable")
                    cur_ok = it.get("orderable")
                    # 之前明確缺貨/不可訂購，現在變成可訂購 => 補貨
                    if prev_ok is False and cur_ok is True:
                        events.append(("restock", shop_key, it))
                new_state[oid] = {
                    "orderable": it["orderable"],
                    "title": it["title"],
                }
        state["shops"][shop_key] = new_state
    return events, new_shops


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_once(cfg, state_path, notify=True):
    state = load_state(state_path)
    kw_re = compile_kw_re(cfg)
    exclude_re = compile_exclude_re(cfg)
    events, new_shops = detect_events(cfg, state, kw_re, exclude_re)
    save_state(state_path, state)

    bot_token, chat_id = resolve_telegram(cfg)
    if not bot_token or not chat_id:
        log("警告：Telegram Bot Token / Chat ID 未設定，無法發送通知。"
            "請設定環境變數 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID（或 GitHub Secrets）。")

    # 首次建立基準：可選送一則啟動摘要
    if new_shops and notify and cfg.get("first_run_notify", True):
        summary = ["🎯 爆旋陀螺監測已啟動，首次掃描完成（此為基準，之後有新貨才會通知）", ""]
        for key, n in new_shops:
            summary.append(f"・{cfg['shops'][key]['name']}：{n} 件")
        try:
            telegram_send_message(bot_token, chat_id, "\n".join(summary))
        except Exception as e:
            log(f"Telegram 摘要發送失敗：{e}")

    if not events:
        log("本次無新貨或補貨事件")
        return 0

    sent = 0
    for kind, shop_key, item in events:
        shop_name = cfg["shops"][shop_key]["name"]
        if notify:
            if notify_item(bot_token, chat_id, kind, shop_name, item):
                sent += 1
                log(f"已通知：{kind} - {item.get('title', '')[:40]}")
        else:
            log(f"[{kind}] {shop_name}: {item.get('title', '')[:40]}")
    log(f"共 {len(events)} 個事件，成功發送 {sent} 則通知")
    return len(events)


def scan_only(cfg):
    kw_re = compile_kw_re(cfg)
    exclude_re = compile_exclude_re(cfg)
    for shop_key, shop_cfg in cfg["shops"].items():
        if not shop_cfg.get("enabled", True):
            continue
        try:
            items = scrape_shop(shop_key, shop_cfg, cfg, kw_re, exclude_re)
        except Exception as e:
            log(f"[{shop_key}] 掃描失敗：{e}")
            continue
        print(f"\n===== {shop_cfg['name']}（{shop_key}）共 {len(items)} 件 =====")
        for it in items:
            status = it.get("status") or "狀態未知"
            print(f"  [{status}] {it['title'][:70]}")
            print(f"       {it['url']}")


def compile_kw_re(cfg):
    parts = [re.escape(k) for k in cfg.get("keywords") or []]
    code = cfg.get("code_pattern")
    if code:
        parts.append(code)
    return re.compile("|".join(parts), re.IGNORECASE)


def compile_exclude_re(cfg):
    parts = [re.escape(k) for k in cfg.get("exclude_keywords") or []]
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def matches(kw_re, exclude_re, text):
    """文字符合關鍵字，且不含排除關鍵字。"""
    if not kw_re.search(text):
        return False
    if exclude_re is not None and exclude_re.search(text):
        return False
    return True


def send_test(cfg):
    token, chat = resolve_telegram(cfg)
    if not token or not chat:
        log("錯誤：缺少 Telegram Bot Token / Chat ID。請設定環境變數 "
            "TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID，或填寫 config.json。")
        return
    try:
        ok = telegram_send_message(token, chat, "✅ 爆旋陀螺監測測試訊息：Telegram 設定正確！")
        log("測試訊息已送出" if ok else "Telegram 回傳 ok=false")
    except Exception as e:
        log(f"測試訊息失敗：{e}")


def main():
    parser = argparse.ArgumentParser(description="爆旋陀螺網店監測")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="設定檔路徑")
    parser.add_argument("--scan", action="store_true", help="只掃描列出商品，不通知")
    parser.add_argument("--test", action="store_true", help="送測試訊息")
    parser.add_argument("--loop", type=int, metavar="MINUTES", help="每隔 N 分鐘執行一次")
    parser.add_argument("--dry-run", action="store_true", help="偵測但不實際發送通知")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if args.test:
        send_test(cfg)
        return
    if args.scan:
        scan_only(cfg)
        return

    state_path = os.path.join(BASE_DIR, cfg.get("state_file", "state.json"))

    if args.loop:
        minutes = max(1, args.loop)
        log(f"常駐模式：每 {minutes} 分鐘執行一次（Ctrl+C 停止）")
        while True:
            try:
                run_once(cfg, state_path, notify=not args.dry_run)
            except Exception as e:
                log(f"執行錯誤：{e}")
            log(f"休眠 {minutes} 分鐘…")
            time.sleep(minutes * 60)
    else:
        run_once(cfg, state_path, notify=not args.dry_run)


if __name__ == "__main__":
    main()
