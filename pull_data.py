#!/usr/bin/env python3
"""Cardia — auto-pull Meta Ads + Adjust data cho phân tích UA.
Đọc credential từ file .env cùng thư mục. Xuất CSV vào ./exports/<YYYY-MM-DD>/.
Chỉ dùng thư viện chuẩn của Python 3 — KHÔNG cần pip install.

Chạy:  python3 pull_data.py
"""
import os, sys, csv, json, datetime, urllib.parse, urllib.request, urllib.error, pathlib

HERE = pathlib.Path(__file__).resolve().parent
META_API_VERSION = "v21.0"
META_API = f"https://graph.facebook.com/{META_API_VERSION}"

# Field Meta ổn định, ai cũng dùng — KHÔNG cần chỉnh
META_FIELDS = ",".join([
    "campaign_name", "adset_name", "ad_name", "spend", "impressions", "reach",
    "clicks", "ctr", "inline_link_click_ctr", "cpm", "actions",
    "cost_per_action_type",
    "quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking",
])


def load_env():
    envfile = HERE / ".env"
    if not envfile.exists():
        sys.exit("❌ Chưa có .env — copy .env.example thành .env rồi điền token.")
    env = {}
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {e.code}: {msg[:500]}")


def _action_value(actions, key):
    for a in actions or []:
        if a.get("action_type") == key:
            return a.get("value", "")
    return ""


def write_meta_csv(rows, path):
    cols = ["date", "campaign_name", "adset_name", "ad_name", "spend", "impressions",
            "reach", "clicks", "ctr", "inline_link_click_ctr", "cpm",
            "installs", "video_3s", "cost_per_install",
            "quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            installs = (_action_value(r.get("actions"), "mobile_app_install")
                        or _action_value(r.get("actions"), "omni_app_install"))
            cpi = _action_value(r.get("cost_per_action_type"), "mobile_app_install")
            v3 = _action_value(r.get("actions"), "video_view")  # 3-second video views
            w.writerow([
                r.get("date_start", ""),
                r.get("campaign_name", ""), r.get("adset_name", ""), r.get("ad_name", ""),
                r.get("spend", ""), r.get("impressions", ""), r.get("reach", ""),
                r.get("clicks", ""), r.get("ctr", ""), r.get("inline_link_click_ctr", ""),
                r.get("cpm", ""), installs, v3, cpi,
                r.get("quality_ranking", ""), r.get("engagement_rate_ranking", ""),
                r.get("conversion_rate_ranking", ""),
            ])


def pull_meta(env, since, until, outdir):
    token = env.get("META_ACCESS_TOKEN")
    acct = env.get("META_AD_ACCOUNT_ID")
    if not token or not acct:
        print("⚠️  Bỏ qua Meta — thiếu META_ACCESS_TOKEN / META_AD_ACCOUNT_ID")
        return
    for level in ("campaign", "ad"):
        params = {
            "level": level,
            "fields": META_FIELDS,
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1",   # breakdown theo NGÀY (cho phép lọc thời gian ở dashboard)
            "limit": "500",
            "access_token": token,
        }
        url = f"{META_API}/{acct}/insights?" + urllib.parse.urlencode(params)
        rows = []
        while url:
            data = json.loads(http_get(url))
            rows.extend(data.get("data", []))
            url = data.get("paging", {}).get("next")
        out = outdir / f"meta_{level}.csv"
        write_meta_csv(rows, out)
        print(f"✅ Meta {level}: {len(rows)} dòng → {out.name}")

    # Spend theo COUNTRY (breakdown=country, level campaign) — Meta /insights KHÔNG có country
    # ở pull chính nên xin riêng. Lỗi ở đây KHÔNG làm hỏng pull chính.
    try:
        gparams = {
            "level": "campaign",
            "fields": "campaign_name,spend,impressions,clicks,actions",
            "breakdowns": "country",
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1",
            "limit": "500",
            "access_token": token,
        }
        gurl = f"{META_API}/{acct}/insights?" + urllib.parse.urlencode(gparams)
        grows = []
        while gurl:
            gdata = json.loads(http_get(gurl))
            grows.extend(gdata.get("data", []))
            gurl = gdata.get("paging", {}).get("next")
        gout = outdir / "meta_campaign_geo.csv"
        with open(gout, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "campaign_name", "country", "spend", "impressions", "clicks", "installs"])
            for r in grows:
                inst = (_action_value(r.get("actions"), "mobile_app_install")
                        or _action_value(r.get("actions"), "omni_app_install"))
                w.writerow([r.get("date_start", ""), r.get("campaign_name", ""),
                            r.get("country", ""), r.get("spend", ""),
                            r.get("impressions", ""), r.get("clicks", ""), inst])
        print(f"✅ Meta campaign×country: {len(grows)} dòng → {gout.name}")
    except Exception as e:
        print(f"⚠️  Bỏ qua Meta campaign×country (không ảnh hưởng pull chính): {e}")

    # Spend theo COUNTRY ở level AD (creative) — cho breakdown country của bảng Creative.
    try:
        aparams = {
            "level": "ad",
            "fields": "ad_name,spend,impressions,clicks,actions",
            "breakdowns": "country",
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1",
            "limit": "500",
            "access_token": token,
        }
        aurl = f"{META_API}/{acct}/insights?" + urllib.parse.urlencode(aparams)
        arows = []
        while aurl:
            adata = json.loads(http_get(aurl))
            arows.extend(adata.get("data", []))
            aurl = adata.get("paging", {}).get("next")
        aout = outdir / "meta_ad_geo.csv"
        with open(aout, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "ad_name", "country", "spend", "impressions", "clicks", "installs"])
            for r in arows:
                inst = (_action_value(r.get("actions"), "mobile_app_install")
                        or _action_value(r.get("actions"), "omni_app_install"))
                w.writerow([r.get("date_start", ""), r.get("ad_name", ""),
                            r.get("country", ""), r.get("spend", ""),
                            r.get("impressions", ""), r.get("clicks", ""), inst])
        print(f"✅ Meta ad×country: {len(arows)} dòng → {aout.name}")
    except Exception as e:
        print(f"⚠️  Bỏ qua Meta ad×country (không ảnh hưởng pull chính): {e}")

    # Trạng thái campaign (ACTIVE/PAUSED…) — KHÔNG có trong /insights, phải hỏi /campaigns.
    try:
        sp = {"fields": "name,effective_status", "limit": "500", "access_token": token}
        surl = f"{META_API}/{acct}/campaigns?" + urllib.parse.urlencode(sp)
        srows = []
        while surl:
            sdata = json.loads(http_get(surl))
            srows.extend(sdata.get("data", []))
            surl = sdata.get("paging", {}).get("next")
        sout = outdir / "meta_campaign_status.csv"
        with open(sout, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["campaign_name", "effective_status"])
            for r in srows:
                w.writerow([r.get("name", ""), r.get("effective_status", "")])
        print(f"✅ Meta campaign status: {len(srows)} dòng → {sout.name}")
    except Exception as e:
        print(f"⚠️  Bỏ qua campaign status (không ảnh hưởng pull chính): {e}")


def _adjust_url(query, since, until):
    if not query.startswith("/"):
        query = "/" + query
    url = "https://automate.adjust.com" + query
    if "date_period" not in url:
        url += f"&date_period={since}:{until}"
    if "format=" not in url:
        url += "&format=csv"
    return url


def pull_adjust(env, since, until, outdir):
    token = env.get("ADJUST_API_TOKEN")
    query = env.get("ADJUST_REPORT_QUERY")
    if not token or not query:
        print("⚠️  Bỏ qua Adjust — thiếu ADJUST_API_TOKEN / ADJUST_REPORT_QUERY")
        return
    hdr = {"Authorization": f"Bearer {token}"}
    body = http_get(_adjust_url(query, since, until), headers=hdr)
    out = outdir / "adjust_report.csv"
    out.write_text(body, encoding="utf-8")
    print(f"✅ Adjust → {out.name}")

    # Query creative-level (tùy chọn) — lỗi ở đây KHÔNG làm hỏng pull chính.
    cq = env.get("ADJUST_CREATIVE_QUERY")
    if cq:
        try:
            cbody = http_get(_adjust_url(cq, since, until), headers=hdr)
            cout = outdir / "adjust_creative.csv"
            cout.write_text(cbody, encoding="utf-8")
            print(f"✅ Adjust creative-level → {cout.name}")
        except Exception as e:
            print(f"⚠️  Bỏ qua Adjust creative-level (không ảnh hưởng pull chính): {e}")


def main():
    env = load_env()
    today = datetime.date.today().isoformat()
    since = env.get("SINCE", "2026-06-13")   # ngày bắt đầu campaign
    until = env.get("UNTIL", today)
    outdir = HERE / "exports" / today
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"📅 Kéo data {since} → {until}\n")
    for name, fn in (("Meta", pull_meta), ("Adjust", pull_adjust)):
        try:
            fn(env, since, until, outdir)
        except Exception as e:
            print(f"❌ {name} lỗi: {e}")
    print(f"\n📂 Xong. Data ở: {outdir}")
    print("→ Báo Claude: 'đã pull data ngày <hôm nay>' để phân tích.")


if __name__ == "__main__":
    main()
