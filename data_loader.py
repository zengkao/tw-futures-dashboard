"""
台指期多時框看板 - 資料載入模組

資料來源:
  1. CSV 檔案 (主要) - 使用者提供的歷史資料
  2. Yahoo Finance (輔助) - ^TWII 台灣加權指數 (近似台指期)
  3. TAIFEX API (輔助) - 期交所即時報價
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 判斷執行環境 (EXE 或 原始碼)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_csv(filepath: str) -> pd.DataFrame:
    """載入CSV資料檔"""
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()

    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Date'] = df['Date'].astype(str).str.strip()

    if 'Time' in df.columns:
        df['Time'] = df['Time'].astype(str).str.strip()
        is_daily = df['Time'].iloc[0] in ('0', '000000', '0.0')
        if is_daily:
            df['datetime'] = pd.to_datetime(df['Date'], format='%Y%m%d')
        else:
            df['Time'] = df['Time'].str.zfill(6)
            df['datetime'] = pd.to_datetime(
                df['Date'] + df['Time'], format='%Y%m%d%H%M%S'
            )
    else:
        df['datetime'] = pd.to_datetime(df['Date'], format='%Y%m%d')

    df = df.set_index('datetime')
    df = df.sort_index()
    df = df[~df.index.duplicated(keep='last')]
    df = df.dropna(subset=['Close'])
    return df


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """重新取樣OHLCV資料到不同時間框架"""
    resampled = df.resample(rule).agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna(subset=['Close'])
    return resampled


def fetch_yfinance_5m() -> pd.DataFrame | None:
    """從Yahoo Finance取得^TWII 5分鐘資料 (最近60天)"""
    try:
        import yfinance as yf
        ticker = yf.Ticker("^TWII")
        df = ticker.history(interval="5m", period="60d")
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df.index.name = 'datetime'
        return df
    except Exception as e:
        print(f"[yfinance 5m] 取得失敗: {e}")
        return None


def fetch_yfinance_daily() -> pd.DataFrame | None:
    """從Yahoo Finance取得^TWII 日線資料"""
    try:
        import yfinance as yf
        ticker = yf.Ticker("^TWII")
        df = ticker.history(interval="1d", period="2y")
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df.index.name = 'datetime'
        return df
    except Exception as e:
        print(f"[yfinance daily] 取得失敗: {e}")
        return None


def fetch_taifex_quote() -> dict | None:
    """嘗試從期交所取得台指期最新報價"""
    try:
        import urllib.request
        import json
        url = (
            "https://mis.taifex.com.tw/futures/api/getQuoteList"
            "?CID=TXF&MarketType=0&SymbolType=F"
        )
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if 'RtData' in data and 'QuoteList' in data['RtData']:
            quotes = data['RtData']['QuoteList']
            if quotes:
                q = quotes[0]
                return {
                    'Open': float(q.get('COpenPrice', 0)),
                    'High': float(q.get('CHighPrice', 0)),
                    'Low': float(q.get('CLowPrice', 0)),
                    'Close': float(q.get('CLastPrice', 0)),
                    'Volume': int(q.get('CTotalVolume', 0)),
                }
        return None
    except Exception as e:
        print(f"[TAIFEX] 取得失敗: {e}")
        return None


def load_all_timeframes(data_dir: str = None, use_online: bool = True) -> dict:
    """
    載入所有時間框架的資料

    Returns:
        dict: key=時間框架名稱, value=DataFrame
              時間框架: '5', '10', '30', '60', '日', '週', '月'
    """
    if data_dir is None:
        data_dir = BASE_DIR

    timeframes = {}
    data_source = "CSV"

    # === 分鐘資料 ===
    csv_5m = os.path.join(data_dir, 'FIMTXN_1.TF_5m.csv')
    df_5m = None

    if os.path.exists(csv_5m):
        df_5m = load_csv(csv_5m)
        data_source = "CSV"

    # 嘗試線上資料補充
    if use_online:
        online_5m = fetch_yfinance_5m()
        if online_5m is not None:
            if df_5m is not None:
                # 合併: 以CSV為主，補充較新的線上資料
                latest_csv = df_5m.index.max()
                new_data = online_5m[online_5m.index > latest_csv]
                if len(new_data) > 0:
                    df_5m = pd.concat([df_5m, new_data])
                    df_5m = df_5m[~df_5m.index.duplicated(keep='last')]
                    data_source = "CSV+YF"
            else:
                df_5m = online_5m
                data_source = "YF"

    if df_5m is not None and len(df_5m) > 0:
        timeframes['5'] = df_5m
        timeframes['10'] = resample_ohlcv(df_5m, '10min')
        timeframes['30'] = resample_ohlcv(df_5m, '30min')
        timeframes['60'] = resample_ohlcv(df_5m, '60min')

    # === 日線資料 ===
    csv_d = os.path.join(data_dir, 'FIMTXN_1.TF_D.csv')
    df_d = None

    if os.path.exists(csv_d):
        df_d = load_csv(csv_d)

    if use_online:
        online_d = fetch_yfinance_daily()
        if online_d is not None:
            if df_d is not None:
                latest_csv = df_d.index.max()
                new_data = online_d[online_d.index > latest_csv]
                if len(new_data) > 0:
                    df_d = pd.concat([df_d, new_data])
                    df_d = df_d[~df_d.index.duplicated(keep='last')]
            else:
                df_d = online_d

    if df_d is not None and len(df_d) > 0:
        timeframes['日'] = df_d
        timeframes['週'] = resample_ohlcv(df_d, 'W')
        try:
            timeframes['月'] = resample_ohlcv(df_d, 'ME')
        except ValueError:
            timeframes['月'] = resample_ohlcv(df_d, 'M')

    timeframes['_source'] = data_source
    return timeframes


def get_latest_price(timeframes: dict) -> dict | None:
    """取得最新報價資訊"""
    for tf_key in ['5', '10', '30', '60', '日']:
        if tf_key in timeframes and len(timeframes[tf_key]) > 0:
            last = timeframes[tf_key].iloc[-1]
            # 嘗試計算漲跌
            if len(timeframes[tf_key]) > 1:
                prev_close = timeframes[tf_key].iloc[-2]['Close']
            else:
                prev_close = last['Open']
            change = last['Close'] - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0
            return {
                'price': last['Close'],
                'open': last['Open'],
                'high': last['High'],
                'low': last['Low'],
                'change': change,
                'change_pct': change_pct,
                'volume': last['Volume'],
                'time': str(timeframes[tf_key].index[-1]),
            }
    return None
