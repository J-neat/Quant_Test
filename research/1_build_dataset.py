# 팩터 연구용 데이터셋 생성: 종목×날짜별 피처 + 미래 수익률
import sys, os, warnings, pickle
warnings.filterwarnings("ignore")
sys.path.insert(0, r"C:\2026_quant"); os.chdir(r"C:\2026_quant")
import numpy as np, pandas as pd, yfinance as yf
from data_collector import get_nasdaq_100, get_kospi_top_100
import FinanceDataReader as fdr
from strategy import calculate_rsi

OUT = sys.argv[1]
START, END = "2020-01-01", "2026-10-16"

def universe():
    u = {t: "NASDAQ" for t in get_nasdaq_100()}
    u.update({t: "KOSPI" for t in get_kospi_top_100()})
    kq = fdr.StockListing('KOSDAQ').head(100)
    u.update({f"{c}.KQ": "KOSDAQ" for c in kq['Code']})
    return u

def heikin_ashi(o, h, l, c):
    ha_c = (o + h + l + c) / 4
    ha_o = np.empty(len(c)); ha_o[0] = (o[0] + c[0]) / 2
    for i in range(1, len(c)):
        ha_o[i] = (ha_o[i-1] + ha_c[i-1]) / 2
    ha_l = np.minimum(l, np.minimum(ha_o, ha_c))
    return ha_o, ha_c, ha_l

def features(df):
    o, h, l, c, v = (df[k].values.astype(float) for k in ["Open", "High", "Low", "Close", "Volume"])
    f = pd.DataFrame(index=df.index)
    close = df["Close"]
    f["rsi"] = calculate_rsi(close).values
    ha_o, ha_c, ha_l = heikin_ashi(o, h, l, c)
    f["ha_body"] = (ha_c - ha_o) / ha_o * 100
    f["ha_strong"] = ((ha_c > ha_o) & np.isclose(ha_l, ha_o)).astype(float)
    sma20 = close.rolling(20).mean()
    f["gap_sma20"] = (close / sma20 - 1) * 100
    f["vol_ratio"] = (df["Volume"] / df["Volume"].rolling(20).mean()).values
    # OBV 비율: 실전처럼 최근 125일 창 시작점 기준 누적
    obv_inc = np.sign(close.diff()).fillna(0).values * v
    C = np.cumsum(obv_inc)
    obv_ratio = np.full(len(c), np.nan)
    for t in range(124, len(c)):
        s = t - 124
        base = C[s]
        obv_t = C[t] - base
        obv_sma = C[t-19:t+1].mean() - base
        obv_ratio[t] = obv_t / obv_sma if obv_sma > 0 else 1.0
    f["obv_ratio"] = obv_ratio
    # POC: 최근 120일 거래량 가중 종가 히스토그램 최빈 구간
    poc = np.full(len(c), np.nan)
    for t in range(119, len(c)):
        hist, edges = np.histogram(c[t-119:t+1], bins=20, weights=v[t-119:t+1])
        k = np.argmax(hist); poc[t] = (edges[k] + edges[k+1]) / 2
    f["poc_gap"] = (c / poc - 1) * 100
    f["high_gap"] = (close / df["High"].rolling(252, min_periods=120).max()).values
    # 후보 팩터
    f["ret_5"] = close.pct_change(5).values
    f["ret_20"] = close.pct_change(20).values
    f["ret_60"] = close.pct_change(60).values
    f["mom_12_1"] = (close.shift(21) / close.shift(252) - 1).values
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1)))); tr[0] = h[0] - l[0]
    f["atr_pct"] = pd.Series(tr, index=df.index).rolling(14).mean().values / c * 100
    f["dist_sma200"] = (close / close.rolling(200).mean() - 1).values
    f["vol_20"] = close.pct_change().rolling(20).std().values * np.sqrt(252)
    f["turnover_5"] = (df["Close"] * df["Volume"]).rolling(5).mean().values
    # 미래 수익률: 다음 날 시가 진입 → t+5 / t+10 종가
    nxt_open = df["Open"].shift(-1)
    f["fwd5"] = (close.shift(-5) / nxt_open - 1).values
    f["fwd10"] = (close.shift(-10) / nxt_open - 1).values
    return f

def main():
    u = universe()
    print("universe", len(u), flush=True)
    raw = yf.download(list(u), start=START, end=END, group_by="ticker", auto_adjust=True, progress=False, threads=True)
    frames = []
    for t, m in u.items():
        try:
            df = raw[t].dropna(subset=["Close"])
            df = df[df["Volume"] > 0]
            if len(df) < 300: continue
            f = features(df)
            f["ticker"], f["market"] = t, m
            frames.append(f.reset_index().rename(columns={"index": "date", "Date": "date"}))
        except Exception as e:
            print("ERR", t, e)
    data = pd.concat(frames, ignore_index=True)
    data = data[data["date"] >= "2021-01-01"]
    data.to_pickle(OUT)
    print("rows", len(data), "tickers", data.ticker.nunique(), data.groupby("market").ticker.nunique().to_dict())

main()
