#!/usr/bin/env python3
"""Tổng hợp Meta + Adjust từ exports/<ngày> mới nhất → in summary để phân tích.
Chạy: python3 analyze.py   (hoặc python3 analyze.py 2026-06-28)
"""
import os, sys, csv, json, re, glob, pathlib
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
CRE_RE = re.compile(r"(CAR_A\d+_[A-Z]+_[A-Z]*\d+_(?:EN|US))")

def latest_export():
    if len(sys.argv) > 1:
        return HERE / "exports" / sys.argv[1]
    dirs = sorted(glob.glob(str(HERE / "exports" / "*")))
    return pathlib.Path(dirs[-1]) if dirs else None

def f(x):
    try: return float(x)
    except: return 0.0

# ---------- ADJUST (USD: installs, cost, ad_revenue) ----------
def analyze_adjust(d):
    rows = json.loads((d / "adjust_report.csv").read_text())["rows"]
    # [installs, cost, rev, ret1*inst, ret7*inst, roas7*cost]
    by_camp = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0.0])
    by_geo  = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0.0])
    tot = [0,0.0,0.0,0.0,0.0,0.0]
    GEO = {"India":"India","United States":"US","Pakistan":"Pakistan","Brazil":"Brazil"}
    LATAM = {"Venezuela, Bolivarian Republic Of","Peru","Colombia","Chile","Argentina",
             "Bolivia, Plurinational State Of","Paraguay","Uruguay","Ecuador","Mexico"}
    for r in rows:
        net = (r.get("network", "") or "").strip().lower()
        if net == "organic" or (not net and (r.get("campaign", "") or "").strip().lower() == "unknown"):
            continue  # bỏ Organic — chỉ đo paid UA (như dashboard)
        ins, cost, rev = int(f(r["installs"])), f(r["cost"]), f(r["ad_revenue"])
        ret1, ret7, roas7 = f(r.get("retention_rate_d1")), f(r.get("retention_rate_d7")), f(r.get("roas_d7"))
        camp = r["campaign"].split(" (")[0]
        c = r["country"]
        geo = GEO.get(c) or ("LATAM" if c in LATAM else "Other")
        for agg,key in ((by_camp,camp),(by_geo,geo)):
            a=agg[key]; a[0]+=ins; a[1]+=cost; a[2]+=rev; a[3]+=ret1*ins; a[4]+=ret7*ins; a[5]+=roas7*cost
        tot[0]+=ins; tot[1]+=cost; tot[2]+=rev; tot[3]+=ret1*ins; tot[4]+=ret7*ins; tot[5]+=roas7*cost
    return by_camp, by_geo, tot

def show(title, agg, sort_by=1):
    print(f"\n### {title}")
    print(f"{'name':<46}{'inst':>6}{'cost$':>9}{'rev$':>8}{'CPI$':>7}{'ROAS':>6}{'LTV$':>6}{'D1%':>6}{'D7%':>5}{'roasD7':>7}")
    for k,v in sorted(agg.items(), key=lambda x:-x[1][sort_by]):
        ins,cost,rev,w1,w7,wr7 = v
        cpi = cost/ins if ins else 0
        roas = rev/cost if cost else 0
        ltv = rev/ins if ins else 0
        d1 = w1/ins*100 if ins else 0
        d7 = w7/ins*100 if ins else 0
        rd7 = wr7/cost if cost else 0
        print(f"{k[:45]:<46}{ins:>6}{cost:>9.2f}{rev:>8.2f}{cpi:>7.3f}{roas:>6.3f}{ltv:>6.3f}{d1:>6.1f}{d7:>5.1f}{rd7:>7.3f}")

# ---------- META (VND spend; CTR/hook/QR per creative) ----------
def analyze_meta(d, fx):
    agg = defaultdict(lambda: [0.0,0,0,0,0.0,0])  # spendVND, impr, clicks_link(approx), installs, video3s, n
    qr = {}
    with open(d / "meta_ad.csv") as fp:
        for r in csv.DictReader(fp):
            m = CRE_RE.search(r["ad_name"])
            cid = m.group(1) if m else (r["ad_name"].strip() or "(unnamed)")
            spend=f(r["spend"]); impr=int(f(r["impressions"]))
            lctr=f(r["inline_link_click_ctr"]); ins=int(f(r["installs"]))
            v3=int(f(r["video_3s"]))
            a=agg[cid]
            a[0]+=spend; a[1]+=impr; a[2]+=lctr/100*impr; a[3]+=ins; a[4]+=v3
            if r["quality_ranking"] not in ("","UNKNOWN"): qr[cid]=r["quality_ranking"]
    print(f"\n### META theo creative (FX={fx:,.0f} VND/$)")
    print(f"{'creative':<36}{'impr':>8}{'inst':>6}{'CPI$':>8}{'linkCTR%':>9}{'hook%':>7}  QR")
    for k,v in sorted(agg.items(), key=lambda x:-x[1][1]):
        spend,impr,lc,ins,v3,_ = v
        cpi=(spend/fx)/ins if ins else 0
        ctr=lc/impr*100 if impr else 0
        hook=v3/impr*100 if impr else 0
        print(f"{k[:35]:<36}{impr:>8}{ins:>6}{cpi:>8.3f}{ctr:>9.2f}{hook:>7.1f}  {qr.get(k,'-')}")
    return agg

# ---------- SESSION CHECK (retention thật hay tracking đứt) ----------
def session_check(d):
    rows = json.loads((d / "adjust_report.csv").read_text())["rows"]
    if not rows or "sessions" not in rows[0]:
        return
    ins = sum(int(f(r.get("installs"))) for r in rows)
    ses = sum(f(r.get("sessions")) for r in rows)
    dau = sum(f(r.get("daus")) for r in rows)
    if not ins:
        return
    print(f"\n### SESSION CHECK  installs={ins}  sessions={ses:.0f} ({ses/ins:.2f}/inst)  daus={dau:.0f}")
    print("→ sessions>installs = SDK CÓ ghi session quay lại; daus ≈ install/ngày = ít người quay lại (retention thật thấp).")


# ---------- ADJUST creative-level (nếu có adjust_creative.csv) ----------
def analyze_adjust_creative(d):
    path = d / "adjust_creative.csv"
    if not path.exists():
        return
    try:
        rows = json.loads(path.read_text())["rows"]
    except Exception as e:
        print(f"\n(adjust_creative.csv có nhưng không đọc được: {e})")
        return
    agg = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])  # inst, cost, rev, ret1*inst, roas7*cost
    for r in rows:
        if (r.get("network", "") or "").strip().lower() == "organic":
            continue
        name = r.get("creative") or r.get("adgroup") or r.get("campaign", "?")
        ins = int(f(r.get("installs"))); cost = f(r.get("cost")); rev = f(r.get("ad_revenue"))
        a = agg[name]; a[0] += ins; a[1] += cost; a[2] += rev
        a[3] += f(r.get("retention_rate_d1")) * ins; a[4] += f(r.get("roas_d7")) * cost
    print("\n### ADJUST theo CREATIVE/ADGROUP (retention chất lượng install)")
    print(f"{'name':<40}{'inst':>6}{'cost$':>9}{'CPI$':>8}{'LTV$':>7}{'D1%':>6}{'roasD7':>7}")
    for k, v in sorted(agg.items(), key=lambda x: -x[1][0]):
        ins, cost, rev, w1, wr7 = v
        print(f"{str(k)[:39]:<40}{ins:>6}{cost:>9.2f}{cost/ins if ins else 0:>8.3f}"
              f"{rev/ins if ins else 0:>7.3f}{w1/ins*100 if ins else 0:>6.1f}{wr7/cost if cost else 0:>7.3f}")


def main():
    d = latest_export()
    print(f"📂 {d}")
    by_camp, by_geo, tot = analyze_adjust(d)
    # FX từ tổng spend Meta(VND) / tổng cost Adjust(USD)
    meta_vnd = sum(f(r["spend"]) for r in csv.DictReader(open(d/"meta_ad.csv")))
    fx = meta_vnd/tot[1] if tot[1] else 24500
    show("ADJUST theo GEO (USD chuẩn)", by_geo)
    show("ADJUST theo CAMPAIGN (USD chuẩn)", by_camp)
    analyze_meta(d, fx)
    analyze_adjust_creative(d)
    session_check(d)
    ins,cost,rev = tot[0],tot[1],tot[2]
    print(f"\n### TỔNG (Adjust): installs={ins}  cost=${cost:.2f}  rev=${rev:.2f}  "
          f"CPI=${cost/ins:.3f}  ROAS={rev/cost:.3f}  LTV=${rev/ins:.3f}  "
          f"D1={tot[3]/ins*100:.1f}%  roasD7={tot[5]/cost:.3f}")

if __name__ == "__main__":
    main()
