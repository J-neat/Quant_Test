import sys, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
d = pd.read_pickle(sys.argv[1])
d["group"] = np.where(d.market == "NASDAQ", "NASDAQ", "KR")
d = d[((d.group == "NASDAQ") & (d.turnover_5 >= 1e7)) | ((d.group == "KR") & (d.turnover_5 >= 1e10))]
d = d[d.bull].dropna(subset=["fwd10", "rsi", "gap_sma20", "poc_gap", "high_gap", "vol_ratio"])
d["fwd10_x"] = d.fwd10 - d.groupby(["group", "date"]).fwd10.transform("mean")
d["period"] = np.where(d.date < "2024-01-01", "train", "test")
clip = lambda x: np.clip(x, 0, 1)
def rsi_score(r, m):
    return np.select([r < 40, r <= 65, r <= 85], [m * r / 40, m, m * (85 - r) / 20], -m * 0.5)
ha = np.where(d.ha_body < 0, np.maximum(-20, d.ha_body / 3 * 20), np.where(d.ha_strong > 0, np.minimum(15, d.ha_body / 3 * 15), 0))
gap = np.where(d.gap_sma20 > 0, np.minimum(15, d.gap_sma20 / 3 * 15), 0)
poc = np.where(d.poc_gap > 0, np.minimum(15, d.poc_gap / 3 * 15), 0)
d["old_kr"] = ha + rsi_score(d.rsi, 15) + gap + np.minimum(15, d.vol_ratio / 2 * 15) + poc
d["old_us"] = ha + 20 * clip((d.high_gap - .85) / .1) + rsi_score(d.rsi, 15) + 15 * clip(d.vol_ratio - 1) + gap + poc
d["hg"] = 40 * clip((d.high_gap - .75) / .20)
d["new_kr"] = d.hg + rsi_score(d.rsi, 15) + gap + poc + np.minimum(15, d.vol_ratio / 2 * 15)   # 단기 항목 유지 + 고가근접 40
d["rand"] = np.random.default_rng(0).random(len(d))
def topn(sub, col, n=5):
    p = sub.sort_values(col, ascending=False).groupby("date").head(n)
    return p.fwd10_x.mean() * 100, (p.fwd10_x > 0).mean() * 100, p.fwd10.mean() * 100
for grp, cols in [("KR", ["rand", "old_kr", "hg", "new_kr"]), ("NASDAQ", ["rand", "old_us", "hg"])]:
    print(f"\n=== {grp}: 매일 상위 5종목, 10일 보유 (초과수익% / 초과 승률% / 절대수익%) ===")
    for per in ["train", "test"]:
        sub = d[(d.group == grp) & (d.period == per)]
        print(per, "  ".join(f"{c}: {a:+.2f} / {b:.0f} / {e:+.2f}" for c in cols for a, b, e in [topn(sub, c)]))

print("\n=== KR 연도별 상위 5종목 10일 초과수익% (rand / old / hg / hg+ha) ===")
d["hg_ha"] = d.hg + ha
k = d[d.group == "KR"]
for y, sub in k.groupby(k.date.dt.year):
    print(y, sub.date.nunique(), "일", "  ".join(f"{c} {topn(sub, c)[0]:+.2f}" for c in ["rand", "old_kr", "hg", "hg_ha"]))
print("\n=== KR 고가근접 점수(60점 만점: 고가 75%→0, 95%→60) 기준점별 (하루 평균 건수 / 초과수익% / 승률%) ===")
k = k.assign(hg60=60 * clip((k.high_gap - .75) / .20))
days = k.date.nunique()
for th in [45, 50, 55, 58, 60]:
    for per in ["train", "test"]:
        s = k[(k.hg60 >= th) & (k.period == per)]; nd = k[k.period == per].date.nunique()
        print(f"th {th} {per}: {len(s)/nd:5.1f}건/일  {s.fwd10_x.mean()*100:+.2f}%  {(s.fwd10_x>0).mean()*100:.0f}%")

print("\n=== KR 고가근접(60)+하이킨아시 기준점별 (건수/일, 초과수익%, 승률%, 절대수익%) / 기존 old_kr 50점 비교 ===")
k = k.assign(new=k.hg60 + ha[d.group.values == "KR"])
for th in [65, 68, 70, 72]:
    for per in ["train", "test"]:
        s = k[(k.new >= th) & (k.period == per)]; nd = k[k.period == per].date.nunique()
        print(f"th {th} {per}: {len(s)/nd:5.1f}건/일  {s.fwd10_x.mean()*100:+.2f}%  {(s.fwd10_x>0).mean()*100:.0f}%  {s.fwd10.mean()*100:+.2f}%")
for per in ["train", "test"]:
    s = k[(k.old_kr >= 50) & (k.period == per)]; nd = k[k.period == per].date.nunique()
    print(f"old>=50 {per}: {len(s)/nd:5.1f}건/일  {s.fwd10_x.mean()*100:+.2f}%  {(s.fwd10_x>0).mean()*100:.0f}%  {s.fwd10.mean()*100:+.2f}%")

print("\n=== 신호 요일별 10일 초과수익% (KR new>=70 / NASDAQ old_us>=80) ===")
k["wd"] = k.date.dt.weekday
n = d[d.group == "NASDAQ"].assign(wd=lambda x: x.date.dt.weekday)
for per in ["train", "test"]:
    a = k[(k.new >= 70) & (k.period == per)].groupby("wd").fwd10_x.mean() * 100
    b = n[(n.old_us >= 80) & (n.period == per)].groupby("wd").fwd10_x.mean() * 100
    print(per, "KR", a.round(2).to_dict(), "| US", b.round(2).to_dict())
