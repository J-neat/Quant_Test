import sys, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
d = pd.read_pickle(sys.argv[1])
reg = {}
for m, idx in {"NASDAQ": "QQQ", "KOSPI": "^KS11", "KOSDAQ": "^KQ11"}.items():
    x = yf.download(idx, start="2019-01-01", end="2026-10-16", auto_adjust=True, progress=False)
    if isinstance(x.columns, pd.MultiIndex): x.columns = x.columns.get_level_values(0)
    reg[m] = (x["Close"] > x["Close"].rolling(200).mean())
d["bull"] = False
for m, s in reg.items():
    mask = d.market == m
    d.loc[mask, "bull"] = s.reindex(pd.DatetimeIndex(d.loc[mask, "date"]), method="ffill").fillna(True).values
d.to_pickle(sys.argv[1].replace(".pkl", "_reg.pkl"))
print(d.groupby(["market", d.date.dt.year]).bull.mean().unstack().round(2))
d["group"] = np.where(d.market == "NASDAQ", "NASDAQ", "KR")
d = d[((d.group == "NASDAQ") & (d.turnover_5 >= 1e7)) | ((d.group == "KR") & (d.turnover_5 >= 1e10))]
d = d[d.bull]
d["fwd10_x"] = d.fwd10 - d.groupby(["group", "date"]).fwd10.transform("mean")
d["period"] = np.where(d.date < "2024-01-01", "train", "test")
FEATS = ["rsi", "ha_body", "ha_strong", "gap_sma20", "vol_ratio", "obv_ratio", "poc_gap", "high_gap",
         "ret_5", "ret_20", "ret_60", "mom_12_1", "atr_pct", "dist_sma200", "vol_20"]
rows = []
for grp in ["NASDAQ", "KR"]:
    for per in ["train", "test"]:
        sub = d[(d.group == grp) & (d.period == per)]
        dates = sorted(sub.date.unique())[::5]
        sub5 = sub[sub.date.isin(dates)]
        for f in FEATS:
            ics = sub5.groupby("date").apply(lambda g: g[[f, "fwd10_x"]].dropna().rank().corr().iloc[0, 1] if g[f].notna().sum() >= 20 else np.nan).dropna()
            rows.append((grp, per, f, ics.mean(), ics.mean() / ics.std() * np.sqrt(len(ics)), len(ics)))
r = pd.DataFrame(rows, columns=["group", "period", "feat", "IC", "t", "n"])
pd.set_option("display.width", 200)
for grp in ["NASDAQ", "KR"]:
    x = r[r.group == grp].pivot(index="feat", columns="period", values=["IC", "t"]).round(3)
    print(f"\n=== {grp} 상승장만 (10일 초과수익) n={r[r.group==grp].groupby('period').n.max().to_dict()} ===")
    print(x.sort_values(("t", "train")).to_string())
