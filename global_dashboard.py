"""
全球期貨 多時框技術分析看板

12 商品 × 7 時框 × 7 指標
每 5 分鐘自動更新報價 + 堆疊資料計算指標

商品: 小台指/NQ/小道瓊/小日經/KOSPI200/白銀/黃金/原油/比特幣/10年美債/日圓/台幣
時框: 5分/10分/30分/60分/日/週/月
指標: 本根/KD/MA/VWAP/MC/SAR/ST

資料來源: Yahoo Finance (免費、免 API Key)
配色: 紅漲綠跌 (台灣慣例)

啟動後自動開啟瀏覽器 → http://127.0.0.1:8777
"""

import json
import time
import os
import sys
import webbrowser
import ssl
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.request import urlopen, Request
from urllib.parse import quote as urlquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ── 路徑 ──────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

from data_loader import resample_ohlcv
from indicators import calculate_all_signals

# ── 設定 ──────────────────────────────────────────────
PORT = 8777
REFRESH_INTERVAL = 300          # 秒 (5 分鐘)

INSTRUMENTS = [
    {"id": "twii",  "name": "小台指",   "sub": "Mini TAIEX",  "symbol": "^TWII",   "decimals": 0},
    {"id": "nq",    "name": "NQ期貨",   "sub": "Nasdaq 100",  "symbol": "NQ=F",    "decimals": 2},
    {"id": "ym",    "name": "小道瓊",   "sub": "Dow Jones",   "symbol": "YM=F",    "decimals": 0},
    {"id": "niy",   "name": "小日經",   "sub": "Nikkei 225",  "symbol": "NIY=F",   "decimals": 0},
    {"id": "kospi", "name": "KOSPI200", "sub": "Korea 200",   "symbol": "^KS200",  "decimals": 2},
    {"id": "gc",    "name": "黃金",     "sub": "COMEX Gold",   "symbol": "GC=F",    "decimals": 2},
    {"id": "si",    "name": "白銀",     "sub": "COMEX Silver", "symbol": "SI=F",    "decimals": 3},
    {"id": "cl",    "name": "原油",     "sub": "WTI Crude",    "symbol": "CL=F",    "decimals": 2},
    {"id": "btc",   "name": "比特幣",   "sub": "BTC / USD",    "symbol": "BTC-USD", "decimals": 1},
    {"id": "tnx",   "name": "10年美債", "sub": "殖利率 Yield", "symbol": "^TNX",    "decimals": 3, "unit": "%"},
    {"id": "jpy",   "name": "日圓",     "sub": "USD / JPY",    "symbol": "JPY=X",   "decimals": 2},
    {"id": "twd",   "name": "台幣",     "sub": "USD / TWD",    "symbol": "TWD=X",   "decimals": 3},
]

TF_ORDER = ["5分", "10分", "30分", "60分", "日", "週", "月"]
IND_KEYS = ["本根", "KD", "MA", "VWAP", "MC", "SAR", "ST"]

# ── 快取 ──────────────────────────────────────────────
_data_cache = {"payload": '{"instruments":[]}'}
_ssl_ctx = ssl.create_default_context()


# ── 即時報價 (v8/chart，輕量快速) ─────────────────────
def _fetch_price(symbol):
    encoded = urlquote(symbol, safe="")
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/"
        f"{encoded}?interval=1d&range=1d"
    )
    req = Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    try:
        with urlopen(req, timeout=10, context=_ssl_ctx) as resp:
            body = json.loads(resp.read().decode())
        meta = body["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta.get("chartPreviousClose", price)
        return {
            "price": price,
            "prevClose": prev,
            "change": round(price - prev, 6),
            "changePct": round(
                ((price - prev) / prev * 100) if prev else 0, 4
            ),
            "currency": meta.get("currency", "USD"),
        }
    except Exception:
        return None


# ── 指標計算 (yfinance OHLCV → 7 時框 × 7 指標) ─────
def _compute_one(inst):
    """取得一個商品的 OHLCV 資料，建構時框並計算所有指標。"""
    import yfinance as yf

    symbol = inst["symbol"]
    try:
        ticker = yf.Ticker(symbol)
    except Exception:
        return _empty_result(inst["id"])

    # ---- 取得 OHLCV ----
    df_5m = _safe_history(ticker, "5m", "60d")
    df_daily = _safe_history(ticker, "1d", "2y")

    # ---- 建構時框 ----
    timeframes = {}

    if df_5m is not None and len(df_5m) >= 30:
        timeframes["5分"] = df_5m
        for label, rule, minlen in [
            ("10分", "10min", 26),
            ("30分", "30min", 26),
            ("60分", "60min", 15),
        ]:
            resampled = resample_ohlcv(df_5m, rule)
            if len(resampled) >= minlen:
                timeframes[label] = resampled

    if df_daily is not None and len(df_daily) >= 30:
        timeframes["日"] = df_daily
        rw = resample_ohlcv(df_daily, "W")
        if len(rw) >= 10:
            timeframes["週"] = rw
        try:
            rm = resample_ohlcv(df_daily, "ME")
        except ValueError:
            rm = resample_ohlcv(df_daily, "M")
        if len(rm) >= 5:
            timeframes["月"] = rm

    # ---- 逐時框計算指標 ----
    tf_results = []
    for tf_name in TF_ORDER:
        if tf_name not in timeframes:
            tf_results.append(_na_tf(tf_name))
            continue
        try:
            signals = calculate_all_signals(timeframes[tf_name])
            score = sum(signals.get(k, 0) for k in IND_KEYS[1:])
            summary = "偏多" if score > 0 else ("偏空" if score < 0 else "中性")
            tf_results.append({
                "name": tf_name,
                "signals": signals,
                "score": score,
                "summary": summary,
            })
        except Exception:
            tf_results.append(_na_tf(tf_name))

    has_data = any(r["signals"] is not None for r in tf_results)
    return {
        "id": inst["id"],
        "timeframes": tf_results,
        "status": "ok" if has_data else "no_data",
    }


def _safe_history(ticker, interval, period):
    try:
        raw = ticker.history(interval=interval, period=period)
        if raw is not None and len(raw) > 0:
            return raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        pass
    return None


def _na_tf(name):
    return {"name": name, "signals": None, "score": None, "summary": "N/A"}


def _empty_result(inst_id):
    return {
        "id": inst_id,
        "timeframes": [_na_tf(tf) for tf in TF_ORDER],
        "status": "error",
    }


# ── 全部更新 ─────────────────────────────────────────
def refresh_all(verbose=True):
    t0 = time.time()

    # Phase 1: 計算指標 (慢，平行)
    signals = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_compute_one, inst): inst for inst in INSTRUMENTS}
        for i, fut in enumerate(as_completed(futs)):
            inst = futs[fut]
            try:
                result = fut.result(timeout=120)
                signals[inst["id"]] = result
                st = "OK" if result.get("status") == "ok" else result.get("status", "?")
            except Exception as e:
                signals[inst["id"]] = _empty_result(inst["id"])
                st = f"FAIL({e})"
            if verbose:
                print(f"  [{i + 1:2d}/{len(INSTRUMENTS)}] {inst['name']:8s} {st}")

    # Phase 2: 即時報價 (快，平行)
    prices = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {
            pool.submit(_fetch_price, inst["symbol"]): inst["id"]
            for inst in INSTRUMENTS
        }
        for fut in as_completed(futs):
            iid = futs[fut]
            try:
                prices[iid] = fut.result(timeout=15)
            except Exception:
                prices[iid] = None

    # Phase 3: 組合
    result = []
    for inst in INSTRUMENTS:
        entry = dict(inst)
        p = prices.get(inst["id"])
        if p:
            entry.update(p)
        else:
            entry["price"] = None
            entry["change"] = 0
            entry["changePct"] = 0
        s = signals.get(inst["id"])
        if s and s.get("timeframes"):
            entry["timeframes"] = s["timeframes"]
        else:
            entry["timeframes"] = [_na_tf(tf) for tf in TF_ORDER]
        result.append(entry)

    elapsed = time.time() - t0
    _data_cache["payload"] = json.dumps(
        {
            "instruments": result,
            "lastUpdate": datetime.now().strftime("%H:%M:%S"),
            "computeSec": round(elapsed, 1),
        },
        ensure_ascii=False,
    )
    if verbose:
        ok = sum(
            1 for v in signals.values() if v and v.get("status") == "ok"
        )
        print(f"\n  完成 {ok}/{len(INSTRUMENTS)} ({elapsed:.1f}s)")


# ── 背景更新 ─────────────────────────────────────────
def _bg_worker():
    while True:
        time.sleep(REFRESH_INTERVAL)
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            print(f"\n  [{ts}] 背景更新 ...")
            refresh_all(verbose=False)
            print(f"  [{ts}] 完成")
        except Exception as e:
            print(f"  [{ts}] 更新失敗: {e}")


# ── HTTP 伺服器 ──────────────────────────────────────
class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            self._json(_data_cache["payload"])
        elif self.path == "/api/refresh":
            threading.Thread(
                target=lambda: refresh_all(verbose=False), daemon=True
            ).start()
            self._json('{"status":"refreshing"}')
        elif self.path in ("/", "/index.html"):
            self._html()
        else:
            self.send_error(404)

    def _json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload.encode())

    def _html(self):
        path = os.path.join(_BASE, "global_dashboard.html")
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "global_dashboard.html not found")

    def log_message(self, *a):
        pass


# ── 主程式 ───────────────────────────────────────────
def main():
    print("=" * 52)
    print("  全球期貨  多時框技術分析看板")
    print("  12 商品 x 7 時框 x 7 指標")
    print("=" * 52)
    print(f"\n  首次計算中 (約 20-40 秒) ...\n")

    refresh_all(verbose=True)

    threading.Thread(target=_bg_worker, daemon=True).start()

    addr = f"http://127.0.0.1:{PORT}"
    print(f"\n  看板網址: {addr}")
    print(f"  每 {REFRESH_INTERVAL // 60} 分鐘自動更新")
    print("  按 Ctrl+C 停止\n")

    server = _Server(("127.0.0.1", PORT), _Handler)
    webbrowser.open(addr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  正在關閉 ...")
        server.shutdown()


if __name__ == "__main__":
    main()
