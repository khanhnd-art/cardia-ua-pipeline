#!/usr/bin/env python3
"""Cardia — sinh báo cáo tuần (Markdown) từ exports/<ngày> mới nhất.
Chạy:  python3 weekly_report.py            -> dùng export mới nhất
       python3 weekly_report.py 2026-06-28 -> chọn ngày cụ thể
Ghi ra: ../../05-analytics-reporting/weekly/<ngày>.md
Auto-flag: CPI cao, Quality Ranking dưới ngưỡng, retention báo động, rò geo LATAM.
Số do script tính; phần "Nhận định & đề xuất" để Claude/người viết tay sau.
"""
import sys, csv, json, re, glob, pathlib
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
OUTDIR = (HERE / ".." / ".." / "05-analytics-reporting" / "weekly").resolve()
CRE_RE = re.compile(r"(CAR_A\d+_[A-Z]+_H\d+_(?:EN|US))")
GEO = {"India": "India", "United States": "US", "Pakistan": "Pakistan", "Brazil": "Brazil"}
LATAM = {"Venezuela, Bolivarian Republic Of", "Peru", "Colombia", "Chile", "Argentina",
         "Bolivia, Plurinational State Of", "Paraguay", "Uruguay", "Ecuador", "Mexico"}


def f(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def latest_export():
    if len(sys.argv) > 1:
        return HERE / "exports" / sys.argv[1]
    dirs = [d for d in sorted(glob.glob(str(HERE / "exports" / "*"))) if pathlib.Path(d).is_dir()]
    return pathlib.Path(dirs[-1]) if dirs else None


def geo_of(c):
    return GEO.get(c) or ("LATAM" if c in LATAM else "Other")


def load_adjust(d):
    rows = json.loads((d / "adjust_report.csv").read_text())["rows"]
    by_geo = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])  # inst, cost, rev, roas7*cost, ret1*inst
    tot = [0, 0.0, 0.0, 0.0, 0.0]
    days = set()
    for r in rows:
        ins = int(f(r.get("installs"))); cost = f(r.get("cost")); rev = f(r.get("ad_revenue"))
        days.add(r.get("day", ""))
        g = by_geo[geo_of(r.get("country", ""))]
        for a in (g, tot):
            a[0] += ins; a[1] += cost; a[2] += rev
            a[3] += f(r.get("roas_d7")) * cost; a[4] += f(r.get("retention_rate_d1")) * ins
    return by_geo, tot, sorted(x for x in days if x)


def load_meta(d, fx):
    agg = defaultdict(lambda: [0.0, 0, 0.0, 0, 0]); qr = {}
    with open(d / "meta_ad.csv") as fp:
        for r in csv.DictReader(fp):
            m = CRE_RE.search(r["ad_name"]); cid = m.group(1) if m else "(no-CAR-id)"
            a = agg[cid]; impr = int(f(r["impressions"]))
            a[0] += f(r["spend"]); a[1] += impr
            a[2] += f(r["inline_link_click_ctr"]) / 100 * impr
            a[3] += int(f(r["installs"])); a[4] += int(f(r["video_3s"]))
            if r["quality_ranking"] not in ("", "UNKNOWN"):
                qr[cid] = r["quality_ranking"]
    return agg, qr


def main():
    d = latest_export()
    if not d:
        sys.exit("❌ Chưa có export.")
    date = d.name
    by_geo, tot, days = load_adjust(d)
    meta_vnd = sum(f(r["spend"]) for r in csv.DictReader(open(d / "meta_ad.csv")))
    fx = meta_vnd / tot[1] if tot[1] else 25000
    meta, qr = load_meta(d, fx)

    ins, cost, rev = tot[0], tot[1], tot[2]
    cpi = cost / ins if ins else 0
    roas = rev / cost if cost else 0
    d1 = tot[4] / ins * 100 if ins else 0
    rd7 = tot[3] / cost if cost else 0
    rng = f"{days[0]} → {days[-1]}" if days else date

    L = []
    L.append(f"# Báo cáo UA — Cardia · {rng}\n")
    L.append(f"> Tự sinh từ `weekly_report.py` (export {date}). Số = Adjust (USD chuẩn) trừ khi ghi rõ. "
             f"FX ~{fx:,.0f} VND/$. Phần **Nhận định & đề xuất** điền tay/Claude.\n")

    L.append("## 1. Tổng quan (KPI)\n")
    L.append("| Chỉ số | Giá trị | Target | Trạng thái |")
    L.append("|---|---|---|---|")
    L.append(f"| Installs | {ins:,} | — | — |")
    L.append(f"| Spend | ${cost:,.2f} | budget $9,000 | — |")
    L.append(f"| Revenue | ${rev:,.2f} | — | — |")
    L.append(f"| CPI | ${cpi:.3f} | < $0.12 | {'🟢' if cpi < 0.12 else '🟡'} |")
    L.append(f"| ROAS (cum) | {roas:.2f}x | → 1.0x | 🔴 |")
    L.append(f"| D1 retention | {d1:.1f}% | > 10% | {'🟢' if d1 > 10 else '🔴'} |")
    L.append(f"| ROAS D7 cohort | {rd7:.2f}x | ≥ 1.0x | 🔴 |\n")

    L.append("## 2. Theo Geo\n")
    L.append("| Geo | Inst | Cost$ | Rev$ | CPI$ | ROAS | D1% | ROAS D7 |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for k, v in sorted(by_geo.items(), key=lambda x: -x[1][1]):
        gi, gc, gr, gw7, gr1 = v
        L.append(f"| {k} | {gi} | {gc:.2f} | {gr:.2f} | {gc/gi if gi else 0:.3f} | "
                 f"{gr/gc if gc else 0:.2f}x | {gr1/gi*100 if gi else 0:.1f} | {gw7/gc if gc else 0:.2f}x |")
    L.append("")

    L.append("## 3. Theo Creative (Meta)\n")
    L.append("| Creative | Impr | Inst | CPI$ | link CTR | hook 3s | Quality |")
    L.append("|---|--:|--:|--:|--:|--:|---|")
    for k, v in sorted(meta.items(), key=lambda x: -x[1][1]):
        sp, impr, lc, ci, v3 = v
        L.append(f"| {k} | {impr:,} | {ci} | {(sp/fx)/ci if ci else 0:.3f} | "
                 f"{lc/impr*100 if impr else 0:.2f}% | {v3/impr*100 if impr else 0:.1f}% | {qr.get(k,'-')} |")
    L.append("")

    # ---- auto-flags ----
    flags = []
    if d1 < 6:
        flags.append(f"🔴 **Retention báo động** — D1 {d1:.1f}% (target >10%). Nút thắt #1, ROAS không về target nếu không sửa.")
    for k, v in sorted(by_geo.items()):
        gi, gc = v[0], v[1]
        if gc > 5 and gi and gc / gi > 0.4:
            flags.append(f"🟡 **{k} CPI cao** — ${gc/gi:.3f} (inst {gi}, spend ${gc:.2f}). Soi targeting/creative.")
    if by_geo.get("LATAM", [0])[0] > 0:
        lt = by_geo["LATAM"]
        flags.append(f"🟡 **Rò install LATAM** — {lt[0]} inst, ${lt[1]:.2f} spend. Khả năng `Value_US` sai targeting → khoá geo.")
    for k, v in sorted(meta.items(), key=lambda x: -x[1][1]):
        if "BELOW" in qr.get(k, "") and v[1] > 10000:
            flags.append(f"🟡 **{k} Quality Ranking dưới ngưỡng** ({qr[k]}) ở {v[1]:,} impr — sửa hook/creative trước khi CPM tăng.")
    L.append("## 4. Cảnh báo tự động\n")
    L.extend(f"- {x}" for x in flags) if flags else L.append("- (không có cờ tự động)")
    L.append("")

    L.append("## 5. Nhận định & đề xuất *(điền tay / Claude)*\n")
    L.append("- **Thắng/thua tuần này:** \n- **Geo scale/cắt:** \n- **Creative vòng tới:** "
             "\n- **Retention/chất lượng:** \n- **Phân bổ budget tuần sau:** \n")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"{date}.md"
    force = "--force" in sys.argv
    if out.exists() and not force:
        # KHÔNG ghi đè báo cáo đã có (giữ phần nhận định viết tay). Ghi data mới ra file _auto để đối chiếu.
        auto = OUTDIR / f"{date}_auto.md"
        auto.write_text("\n".join(L), encoding="utf-8")
        print(f"↩️  {out.name} đã tồn tại — KHÔNG đè (giữ narrative). Data mới → {auto.name}. Dùng --force để ghi đè.")
        return
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"✅ Báo cáo tuần → {out}")
    print(f"   {rng} · installs={ins} CPI=${cpi:.3f} ROAS={roas:.2f}x D1={d1:.1f}% · {len(flags)} cờ")


if __name__ == "__main__":
    main()
