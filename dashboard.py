#!/usr/bin/env python3
"""Cardia — sinh dashboard HTML self-contained từ exports/<ngày> mới nhất.
Chạy:  python3 dashboard.py            -> ghi dashboard.html (cùng thư mục)
       python3 dashboard.py 2026-06-28 -> chọn ngày cụ thể

Kiến trúc: nhúng TOÀN BỘ data theo NGÀY (Adjust day×geo + Meta day×creative) vào JS;
JS tự tính lại KPI + mini-chart + delta vs-prev + bảng theo cửa sổ thời gian người dùng chọn
(Today / Yesterday / 7D / 14D / 30D / All). Không phụ thuộc thư viện ngoài.
"""
import sys, csv, json, re, glob, pathlib, datetime
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
# hook token: H7, CL06, ... (chữ hoa + số); geo hiện có EN/US
CRE_RE = re.compile(r"(CAR_A\d+_[A-Z]+_[A-Z]*\d+_(?:EN|US))")
# Saya: SAYA_<angle S#>_<format>_<hook#>_<geo>_<TIKTOK|META>
CRE_RE_SAYA = re.compile(r"(SAYA_S\d+_[A-Z]+_[A-Z]*\d+_[A-Z]{2}_(?:TIKTOK|META))")
GEO = {"India": "India", "United States": "US", "Pakistan": "Pakistan", "Brazil": "Brazil"}
LATAM = {"Venezuela, Bolivarian Republic Of", "Peru", "Colombia", "Chile", "Argentina",
         "Bolivia, Plurinational State Of", "Paraguay", "Uruguay", "Ecuador", "Mexico",
         "Guatemala", "Honduras", "Nicaragua", "Costa Rica", "Panama", "El Salvador",
         "Dominican Republic", "Cuba",
         # Caribbean & Guianas → gộp chung LATAM (Latin America & Caribbean)
         "Haiti", "Jamaica", "Trinidad And Tobago", "Guyana", "Suriname", "Belize",
         "French Guiana", "Antigua And Barbuda", "Barbados", "Grenada", "Saint Lucia",
         "Saint Vincent And The Grenadines", "Bahamas", "Dominica", "Saint Kitts And Nevis",
         "Curacao", "Aruba", "Puerto Rico", "Turks And Caicos Islands", "Anguilla"}
# nước → vùng (gom cho gọn; nước không có trong map sẽ hiện thẳng tên nước)
REGION = {k: "South Asia" for k in ("bangladesh", "nepal", "sri lanka", "afghanistan", "bhutan", "maldives")}
REGION.update({k: "SEA" for k in (
    "indonesia", "philippines", "vietnam", "viet nam", "thailand", "malaysia", "myanmar",
    "cambodia", "laos", "lao people's democratic republic", "singapore", "papua new guinea",
    "timor-leste", "east timor", "brunei", "brunei darussalam")})
REGION.update({k: "Middle East" for k in (
    "iraq", "iran", "iran, islamic republic of", "saudi arabia", "united arab emirates",
    "yemen", "jordan", "syria", "syrian arab republic", "lebanon", "israel", "kuwait",
    "qatar", "oman", "bahrain", "turkey", "palestine", "palestine, state of",
    "palestinian territory, occupied")})
REGION.update({k: "Africa" for k in (
    "ethiopia", "south africa", "nigeria", "kenya", "democratic republic of congo", "congo",
    "somalia", "cameroon", "zimbabwe", "zambia", "liberia", "ghana", "algeria", "egypt",
    "morocco", "tunisia", "libya", "sudan", "south sudan", "uganda", "tanzania",
    "tanzania, united republic of", "angola", "mozambique", "senegal", "ivory coast",
    "cote d'ivoire", "mali", "niger", "chad", "rwanda", "burundi", "malawi", "madagascar",
    "botswana", "namibia", "sierra leone", "guinea", "benin", "togo", "burkina faso",
    "mauritania", "gabon", "eritrea", "gambia", "lesotho", "eswatini", "swaziland",
    "comoros", "mauritius", "cape verde", "seychelles", "sao tome and principe", "djibouti",
    "equatorial guinea", "guinea-bissau", "reunion", "mayotte", "central african republic",
    "republic of congo", "saint helena, ascension and tristan da cunha")})
REGION.update({k: "East Asia" for k in (
    "china", "japan", "south korea", "korea, republic of", "taiwan", "hong kong",
    "mongolia", "macao")})
REGION.update({k: "Oceania" for k in (
    "australia", "new zealand", "fiji", "vanuatu", "solomon islands", "samoa", "american samoa",
    "tonga", "kiribati", "marshall islands", "micronesia, federated states of", "nauru",
    "palau", "tuvalu", "cook islands", "niue", "tokelau", "french polynesia", "new caledonia",
    "guam", "papua new guinea")})
REGION.update({k: "Central Asia" for k in (
    "kazakhstan", "uzbekistan", "tajikistan", "kyrgyzstan", "turkmenistan", "azerbaijan",
    "georgia", "armenia")})
REGION.update({k: "Europe" for k in (
    "france", "germany", "poland", "russia", "russian federation", "cyprus", "united kingdom",
    "italy", "spain", "portugal", "netherlands", "belgium", "ireland", "switzerland", "austria",
    "sweden", "norway", "denmark", "finland", "iceland", "greece", "ukraine", "belarus",
    "romania", "bulgaria", "hungary", "czech republic", "czechia", "slovakia", "slovenia",
    "croatia", "serbia", "bosnia and herzegovina", "north macedonia", "macedonia", "albania",
    "montenegro", "kosovo", "moldova", "lithuania", "latvia", "estonia", "luxembourg", "malta",
    "monaco", "andorra", "liechtenstein", "san marino")})
REGION.update({k: "North America" for k in ("canada", "greenland", "bermuda")})


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


_GEO_LC = {k.lower(): v for k, v in GEO.items()}
_LATAM_LC = {x.lower() for x in LATAM}


def geo_of(c):
    low = (c or "").strip().lower()
    if not low or low == "unknown":
        return "Unknown"
    if low in _GEO_LC:
        return _GEO_LC[low]
    if low in _LATAM_LC:
        return "LATAM"
    if low in REGION:
        return REGION[low]
    return c  # nước cụ thể không thuộc vùng nào → hiện thẳng tên nước


def country_of(c):
    """Như geo_of nhưng KHÔNG gom vùng — luôn trả về tên nước (chỉ chuẩn hoá GEO chính).
    Dùng cho bảng Geo: thống kê theo từng country, top 10 + Other."""
    low = (c or "").strip().lower()
    if not low or low == "unknown":
        return "Unknown"
    if low in _GEO_LC:
        return _GEO_LC[low]
    return c.strip()


# ISO-3166 alpha-2 → tên nước (khớp tên Adjust/REGION để geo_of gom đúng vùng).
# Meta breakdown=country trả về mã ISO2; nước thiếu trong map → hiện thẳng mã.
ISO2_NAME = {
    "IN": "India", "US": "United States", "PK": "Pakistan", "BR": "Brazil",
    "BD": "Bangladesh", "NP": "Nepal", "LK": "Sri Lanka", "AF": "Afghanistan",
    "BT": "Bhutan", "MV": "Maldives",
    "ID": "Indonesia", "PH": "Philippines", "VN": "Viet Nam", "TH": "Thailand",
    "MY": "Malaysia", "MM": "Myanmar", "KH": "Cambodia", "LA": "Lao People's Democratic Republic",
    "SG": "Singapore", "PG": "Papua New Guinea", "TL": "East Timor", "BN": "Brunei Darussalam",
    "IQ": "Iraq", "IR": "Iran, Islamic Republic Of", "SA": "Saudi Arabia",
    "AE": "United Arab Emirates", "YE": "Yemen", "JO": "Jordan", "SY": "Syrian Arab Republic",
    "LB": "Lebanon", "IL": "Israel", "KW": "Kuwait", "QA": "Qatar", "OM": "Oman",
    "BH": "Bahrain", "TR": "Turkey", "PS": "Palestinian Territory, Occupied",
    "ET": "Ethiopia", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
    "CD": "Democratic Republic Of Congo", "CG": "Republic Of Congo", "SO": "Somalia",
    "CM": "Cameroon", "ZW": "Zimbabwe", "ZM": "Zambia", "LR": "Liberia", "GH": "Ghana",
    "DZ": "Algeria", "EG": "Egypt", "MA": "Morocco", "TN": "Tunisia", "LY": "Libya",
    "SD": "Sudan", "SS": "South Sudan", "UG": "Uganda", "TZ": "Tanzania, United Republic Of",
    "AO": "Angola", "MZ": "Mozambique", "SN": "Senegal", "CI": "Cote d'Ivoire",
    "ML": "Mali", "NE": "Niger", "TD": "Chad", "RW": "Rwanda", "BI": "Burundi",
    "MW": "Malawi", "MG": "Madagascar", "BW": "Botswana", "NA": "Namibia",
    "SL": "Sierra Leone", "GN": "Guinea", "BJ": "Benin", "TG": "Togo", "BF": "Burkina Faso",
    "MR": "Mauritania", "GA": "Gabon", "ER": "Eritrea", "GM": "Gambia", "LS": "Lesotho",
    "SZ": "Swaziland", "KM": "Comoros", "MU": "Mauritius", "CV": "Cape Verde",
    "SC": "Seychelles", "DJ": "Djibouti", "GQ": "Equatorial Guinea", "GW": "Guinea-bissau",
    "CF": "Central African Republic", "SH": "Saint Helena, Ascension And Tristan Da Cunha",
    "CN": "China", "JP": "Japan", "KR": "South Korea", "TW": "Taiwan", "HK": "Hong Kong",
    "MN": "Mongolia", "MO": "Macao",
    "AU": "Australia", "NZ": "New Zealand", "FJ": "Fiji", "VU": "Vanuatu",
    "SB": "Solomon Islands", "WS": "Samoa", "AS": "American Samoa", "TO": "Tonga",
    "KI": "Kiribati", "MH": "Marshall Islands", "FM": "Micronesia, Federated States Of",
    "NR": "Nauru", "PW": "Palau", "TV": "Tuvalu", "CK": "Cook Islands", "NU": "Niue",
    "TK": "Tokelau", "GU": "Guam",
    "KZ": "Kazakhstan", "UZ": "Uzbekistan", "TJ": "Tajikistan", "KG": "Kyrgyzstan",
    "TM": "Turkmenistan", "AZ": "Azerbaijan", "GE": "Georgia", "AM": "Armenia",
    "FR": "France", "DE": "Germany", "PL": "Poland", "RU": "Russian Federation",
    "CY": "Cyprus", "GB": "United Kingdom", "IT": "Italy", "ES": "Spain", "PT": "Portugal",
    "NL": "Netherlands", "BE": "Belgium", "IE": "Ireland", "CH": "Switzerland",
    "AT": "Austria", "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland",
    "IS": "Iceland", "GR": "Greece", "UA": "Ukraine", "BY": "Belarus", "RO": "Romania",
    "BG": "Bulgaria", "HU": "Hungary", "CZ": "Czech Republic", "SK": "Slovakia",
    "SI": "Slovenia", "HR": "Croatia", "RS": "Serbia", "BA": "Bosnia And Herzegovina",
    "MK": "North Macedonia", "AL": "Albania", "ME": "Montenegro", "MD": "Moldova",
    "LT": "Lithuania", "LV": "Latvia", "EE": "Estonia", "LU": "Luxembourg", "MT": "Malta",
    "CA": "Canada", "GL": "Greenland", "BM": "Bermuda",
    "VE": "Venezuela, Bolivarian Republic Of", "PE": "Peru", "CO": "Colombia",
    "CL": "Chile", "AR": "Argentina", "BO": "Bolivia, Plurinational State Of",
    "PY": "Paraguay", "UY": "Uruguay", "EC": "Ecuador", "MX": "Mexico",
    "GT": "Guatemala", "HN": "Honduras", "NI": "Nicaragua", "CR": "Costa Rica",
    "PA": "Panama", "SV": "El Salvador", "DO": "Dominican Republic", "CU": "Cuba",
    "HT": "Haiti", "JM": "Jamaica", "TT": "Trinidad And Tobago", "GY": "Guyana",
    "SR": "Suriname", "BZ": "Belize", "GF": "French Guiana", "AG": "Antigua And Barbuda",
    "BB": "Barbados", "GD": "Grenada", "LC": "Saint Lucia",
    "VC": "Saint Vincent And The Grenadines", "BS": "Bahamas", "DM": "Dominica",
    "KN": "Saint Kitts And Nevis", "CW": "Curacao", "AW": "Aruba", "PR": "Puerto Rico",
    "TC": "Turks And Caicos Islands", "AI": "Anguilla",
    "VI": "Virgin Islands (US)", "VG": "Virgin Islands (US)", "SX": "Sint Maarten",
    "BQ": "Aruba", "KY": "Cayman Islands", "MS": "Anguilla",
    "FK": "Falkland Islands", "GP": "Guadeloupe", "MF": "Saint Martin",
    "MP": "Northern Mariana Islands", "MQ": "Martinique", "NC": "New Caledonia",
    "PF": "French Polynesia", "RE": "Reunion", "ST": "Sao Tome And Principe",
    "WF": "Wallis And Futuna", "YT": "Mayotte",
}


def channel_of(network):
    """Suy channel ads từ dimension network của Adjust (Facebook Installs / TikTok ... )."""
    n = (network or "").lower()
    if "tiktok" in n:
        return "TikTok"
    if "facebook" in n or "instagram" in n or "meta" in n:
        return "Meta"
    if "google" in n or "adwords" in n:
        return "Google"
    if "untrusted" in n or "unattributed" in n or not n.strip():
        return ""  # không đủ tin cậy để gán channel
    return network.strip()


def load_adjust(d, fname="adjust_report.csv"):
    """DTOT[day]; DGEO[geo][day]; DACAM[campaign][day]; DCAMGEO[campaign][geo][day]
    — đều =[inst,cost,rev,roas7*cost,ret1*inst]; CAM_CH[campaign]=channel (suy từ network).
    fname: adjust_report.csv (Cardia) / adjust_saya.csv (Saya)."""
    rows = json.loads((d / fname).read_text())["rows"]
    DTOT = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])
    DGEO = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0]))
    DACAM = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0]))
    CAM_CH = {}
    # slot[5]=spend Meta (VND), slot[6]=installs Meta — ghép vào sau từ load_meta_geo()
    DCAMGEO = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0])))
    for r in rows:
        # bỏ Organic — dashboard chỉ đo paid UA (revenue organic làm ROAS "độn" vì spend không có phần đó)
        net = (r.get("network", "") or "").strip().lower()
        if net == "organic" or (not net and (r.get("campaign", "") or "").strip().lower() == "unknown"):
            continue
        day = r.get("day", "")
        ins = int(f(r.get("installs"))); cost = f(r.get("cost")); rev = f(r.get("ad_revenue"))
        roas7 = f(r.get("roas_d7")); ret1 = f(r.get("retention_rate_d1"))
        geo = country_of(r.get("country", ""))  # bảng Geo thống kê theo COUNTRY, không gom vùng
        # DCAMGEO key theo ĐÚNG country (không gom vùng) để so sánh từng nước
        cty = (r.get("country", "") or "").strip() or "Unknown"
        if cty.lower() == "unknown":
            cty = "Unknown"
        # tên Adjust có hậu tố " (id)" → bỏ để khớp tên campaign Meta
        camp = re.sub(r"\s*\(\d+\)\s*$", "", r.get("campaign", "") or "")
        ch = channel_of(r.get("network", ""))
        if ch and not CAM_CH.get(camp):
            CAM_CH[camp] = ch
        for a in (DTOT[day], DGEO[geo][day], DACAM[camp][day]):
            a[0] += ins; a[1] += cost; a[2] += rev; a[3] += roas7 * cost; a[4] += ret1 * ins
        a = DCAMGEO[camp][cty][day]
        a[0] += ins; a[1] += cost; a[2] += rev; a[3] += roas7 * cost; a[4] += ret1 * ins
    return DTOT, DGEO, DACAM, DCAMGEO, CAM_CH


def load_meta(d, fname="meta_ad.csv", cre_re=CRE_RE):
    """DCRE[creative][day]=[spendVND,impr,linkclicks,inst,v3]; QR[creative]=ranking."""
    DCRE = defaultdict(lambda: defaultdict(lambda: [0.0, 0, 0.0, 0, 0]))
    QR = {}
    with open(d / fname) as fp:
        for r in csv.DictReader(fp):
            m = cre_re.search(r.get("ad_name", ""))
            # không match mã CAR → hiện NGUYÊN tên ad đang chạy ở Meta (không gom "(no-CAR-id)")
            cid = m.group(1) if m else (r.get("ad_name", "").strip() or "(unnamed)")
            day = r.get("date", "") or "?"
            impr = int(f(r["impressions"]))
            a = DCRE[cid][day]
            a[0] += f(r["spend"]); a[1] += impr
            a[2] += f(r["inline_link_click_ctr"]) / 100 * impr
            a[3] += int(f(r["installs"])); a[4] += int(f(r["video_3s"]))
            if r.get("quality_ranking", "") not in ("", "UNKNOWN"):
                QR[cid] = r["quality_ranking"]
    return DCRE, QR


ANGLE_NAME = {"A1": "Convenience", "A2": "Family care", "A3": "Reminder", "A4": "Know your numbers",
              "A5": "Awareness", "A6": "Urgency", "A7": "Gestational"}
ANGLE_NAME_SAYA = {"S1": "Speaking anxiety", "S2": "Career", "S3": "5-min habit", "S4": "AI demo",
                   "S5": "Cheaper than tutor", "S6": "Travel", "S7": "Robot skit"}
# bid/optimization strategy suy từ campaign name (ưu tiên theo thứ tự)
OBJ_RULES = [("roas", "ROAS"), ("cpi", "CPI cap"), ("value", "Value"),
             ("broad", "Volume"), ("volume", "Volume"), ("adv", "Advantage+"),
             ("bidding", "Lowest cost"), ("normal", "Lowest cost")]


def objective_of(name):
    low = name.lower()
    for key, label in OBJ_RULES:
        if key in low:
            return label
    return "Install"


def load_meta_campaign(d, fname="meta_campaign.csv", status_fname="meta_campaign_status.csv"):
    """DCAM[campaign][day]=[spendVND,impr,linkclicks,inst,v3]; CAM_OBJ; CAM_STATUS[campaign]=effective_status."""
    DCAM = defaultdict(lambda: defaultdict(lambda: [0.0, 0, 0.0, 0, 0]))
    CAM_OBJ, CAM_STATUS = {}, {}
    p = d / fname
    if not p.exists():
        return DCAM, CAM_OBJ, CAM_STATUS
    with open(p) as fp:
        for r in csv.DictReader(fp):
            cam = (r.get("campaign_name", "") or "(no-name)").strip()
            day = r.get("date", "") or "?"
            impr = int(f(r["impressions"]))
            a = DCAM[cam][day]
            a[0] += f(r["spend"]); a[1] += impr
            a[2] += f(r["inline_link_click_ctr"]) / 100 * impr
            a[3] += int(f(r["installs"])); a[4] += int(f(r["video_3s"]))
            CAM_OBJ[cam] = objective_of(cam)
    sp = d / status_fname
    if sp.exists():
        with open(sp) as fp:
            for r in csv.DictReader(fp):
                cam = (r.get("campaign_name", "") or "").strip()
                if cam:
                    CAM_STATUS[cam] = (r.get("effective_status", "") or "").strip()
    return DCAM, CAM_OBJ, CAM_STATUS


def load_meta_geo(d, fname="meta_campaign_geo.csv"):
    """META_CG[campaign][country][day] = [spend Meta (VND), installs Meta].
    Meta breakdown=country trả mã ISO2 → đổi sang tên nước (khớp tên Adjust) để ghép vào DCAMGEO theo country."""
    META_CG = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0])))
    p = d / fname
    if not p.exists():
        return META_CG
    with open(p) as fp:
        for r in csv.DictReader(fp):
            cam = (r.get("campaign_name", "") or "(no-name)").strip()
            iso = (r.get("country", "") or "").strip().upper()
            name = ISO2_NAME.get(iso, iso)  # thiếu trong map → giữ mã ISO
            day = r.get("date", "") or "?"
            a = META_CG[cam][name][day]
            a[0] += f(r.get("spend")); a[1] += int(f(r.get("installs")))
    return META_CG


def load_adjust_creative(d):
    """DCREGEO[carid][country][day]=[inst,cost,rev,ret1*inst, spendMetaVND, instMeta] — creative × country.
    Key theo ĐÚNG country (không gom vùng). slot[4],[5] ghép sau từ load_meta_creative_geo()."""
    DCG = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0])))
    p = d / "adjust_creative.csv"
    if not p.exists():
        return DCG
    try:
        rows = json.loads(p.read_text())["rows"]
    except Exception:
        return DCG
    for r in rows:
        net = (r.get("network", "") or "").strip().lower()
        if net == "organic":
            continue  # bỏ Organic như load_adjust
        raw = (r.get("creative", "") or "").strip()
        m = CRE_RE.search(raw)
        # không match mã CAR → key theo nguyên tên creative (khớp tên ad Meta nếu trùng)
        cid = m.group(1) if m else (raw or "(unnamed)")
        day = r.get("day", "") or "?"
        cty = (r.get("country", "") or "").strip() or "Unknown"
        if cty.lower() == "unknown":
            cty = "Unknown"
        ins = int(f(r.get("installs"))); cost = f(r.get("cost"))
        rev = f(r.get("ad_revenue")); ret1 = f(r.get("retention_rate_d1"))
        a = DCG[cid][cty][day]
        a[0] += ins; a[1] += cost; a[2] += rev; a[3] += ret1 * ins
    return DCG


def load_meta_creative_geo(d, fname="meta_ad_geo.csv", cre_re=CRE_RE):
    """META_CRG[carid][country][day] = [spend Meta (VND), installs Meta] từ meta_ad_geo.csv (level ad × country)."""
    META_CRG = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0])))
    p = d / fname
    if not p.exists():
        return META_CRG
    with open(p) as fp:
        for r in csv.DictReader(fp):
            raw = (r.get("ad_name", "") or "").strip()
            m = cre_re.search(raw)
            cid = m.group(1) if m else (raw or "(unnamed)")
            iso = (r.get("country", "") or "").strip().upper()
            name = ISO2_NAME.get(iso, iso)
            day = r.get("date", "") or "?"
            a = META_CRG[cid][name][day]
            a[0] += f(r.get("spend")); a[1] += int(f(r.get("installs")))
    return META_CRG


def jnum(x):
    return round(x, 4)


def build(d, app):
    """Sinh 1 trang dashboard cho 1 app.
    app="cardia": Meta + Adjust đầy đủ → dashboard.html
    app="saya":   CHỈ Adjust (spend TikTok đã đẩy sang Adjust qua partner link) → saya.html"""
    is_saya = (app == "saya")
    app_title = "Saya" if is_saya else "Cardia"
    src = "adjust_saya.csv" if is_saya else "adjust_report.csv"
    pfx = "meta_saya" if is_saya else "meta"          # prefix file Meta theo app
    cre_re = CRE_RE_SAYA if is_saya else CRE_RE
    ang_name = ANGLE_NAME_SAYA if is_saya else ANGLE_NAME
    has_meta = (d / f"{pfx}_ad.csv").exists()          # Saya có Meta từ 05/07 (act_3280909035510133)
    date = d.name
    # "Last updated" = giờ PULL THẬT (mtime file Adjust ghi bởi pull_data), KHÔNG phải giờ build UI.
    # → rebuild dashboard không pull lại sẽ không làm đổi số này.
    try:
        pulled_ts = (d / src).stat().st_mtime
    except OSError:
        pulled_ts = datetime.datetime.now().timestamp()
    built = datetime.datetime.fromtimestamp(pulled_ts).strftime("%d/%m/%Y %H:%M")
    DTOT, DGEO, DACAM_ADJ, DCAMGEO, CAM_CH = load_adjust(d, src)
    if has_meta:
        DCRE, QR = load_meta(d, f"{pfx}_ad.csv", cre_re)
        # adjust_creative.csv là query app Cardia → Saya khởi tạo rỗng (nhận merge Meta bên dưới)
        DCREGEO = load_adjust_creative(d) if not is_saya else \
            defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0])))
        DCAM, CAM_OBJ, CAM_STATUS = load_meta_campaign(d, f"{pfx}_campaign.csv", f"{pfx}_campaign_status.csv")
        # ghép spend+installs Meta theo country vào DCAMGEO/DCREGEO (slot spend VND + inst Meta).
        # CANON: chuẩn hoá tên nước về đúng spelling Adjust (lowercase → tên Adjust) để merge khớp.
        META_CG = load_meta_geo(d, f"{pfx}_campaign_geo.csv")
        META_CRG = load_meta_creative_geo(d, f"{pfx}_ad_geo.csv", cre_re)
        CANON = {}
        for src_map in (DCAMGEO, DCREGEO):
            for geos in src_map.values():
                for cty in geos:
                    CANON.setdefault(cty.lower(), cty)
        for cam, geos in META_CG.items():
            for cty, dd in geos.items():
                key = CANON.get(cty.lower(), cty)
                for day, a in dd.items():
                    DCAMGEO[cam][key][day][5] += a[0]
                    DCAMGEO[cam][key][day][6] += a[1]
        for cid, geos in META_CRG.items():
            for cty, dd in geos.items():
                key = CANON.get(cty.lower(), cty)
                for day, a in dd.items():
                    DCREGEO[cid][key][day][4] += a[0]
                    DCREGEO[cid][key][day][5] += a[1]
    else:
        DCRE, QR = {}, {}
        DCREGEO = {}
        DCAM, CAM_OBJ, CAM_STATUS = {}, {}, {}
    # campaign chỉ có trong Adjust (vd TikTok — không có ad-platform API) vẫn cần objective suy từ tên
    for _c in DACAM_ADJ:
        CAM_OBJ.setdefault(_c, objective_of(_c))

    all_days = sorted(DTOT.keys())
    # Adjust thường mở bucket ngày mới sớm hơn Meta (Meta chốt sổ ~14:00 VN, GMT-7). Nếu để ngày
    # Adjust-only mới nhất làm "hôm nay" thì bảng Campaign/Creative (nguồn Meta) rỗng + lệch trục
    # Today/Yesterday. → cắt trục ngày tới ngày Meta mới nhất; ngày sau tự hiện khi Meta chốt sổ (re-fetch).
    if has_meta:
        meta_days = set()
        for _fn in (f"{pfx}_campaign.csv", f"{pfx}_ad.csv"):
            _p = d / _fn
            if _p.exists():
                for _r in csv.DictReader(open(_p)):
                    _dt = (_r.get("date") or "").strip()
                    if _dt:
                        meta_days.add(_dt)
        if meta_days:
            _mmax = max(meta_days)
            all_days = [x for x in all_days if x <= _mmax]
    # FX luôn suy từ CARDIA (Meta VND ÷ Adjust cost USD — cost sharing Cardia đã chuẩn).
    # Saya chưa bật cost sharing Meta→Adjust nên không tự suy được; cùng đơn vị VND nên dùng chung.
    try:
        _mv = sum(f(r["spend"]) for r in csv.DictReader(open(d / "meta_ad.csv")))
        _rows = json.loads((d / "adjust_report.csv").read_text())["rows"]
        _ac = sum(f(r.get("cost")) for r in _rows
                  if (r.get("network", "") or "").strip().lower() != "organic")
        fx = _mv / _ac if _ac else 26000
    except Exception:
        fx = 26000
    # Mốc D1 chín: neo theo NGÀY DATA MỚI NHẤT trong snapshot (không phải hôm nay) — vì retention
    # 1-2 ngày cuối bị đếm thiếu do lúc pull ngày chưa trọn. Install-day X đo được D1 khi X+1 đã
    # trọn ngày & đã settle → X <= (ngày mới nhất - 2). Cohort mới hơn → "chưa chín", D1 hiển thị "–".
    _last = all_days[-1] if all_days else datetime.date.today().isoformat()
    d1cut = (datetime.date.fromisoformat(_last) - datetime.timedelta(days=2)).isoformat()

    # ----- đóng gói JSON cho JS -----
    j_days = json.dumps(all_days)
    j_dtot = json.dumps({k: [v[0]] + [jnum(x) for x in v[1:]] for k, v in DTOT.items()})
    j_dgeo = json.dumps({g: {dy: [a[0]] + [jnum(x) for x in a[1:]] for dy, a in days.items()}
                         for g, days in DGEO.items()})
    j_dcre = json.dumps({c: {dy: [jnum(a[0]), a[1], jnum(a[2]), a[3], a[4]] for dy, a in days.items()}
                         for c, days in DCRE.items()})
    j_dcam = json.dumps({c: {dy: [jnum(a[0]), a[1], jnum(a[2]), a[3], a[4]] for dy, a in days.items()}
                         for c, days in DCAM.items()})
    j_cobj = json.dumps(CAM_OBJ)
    j_cstat = json.dumps(CAM_STATUS, ensure_ascii=False)
    j_dacam = json.dumps({c: {dy: [a[0]] + [jnum(x) for x in a[1:]] for dy, a in days.items()}
                          for c, days in DACAM_ADJ.items()}, ensure_ascii=False)
    j_camch = json.dumps(CAM_CH, ensure_ascii=False)
    # creative×country: [adjInst, costAdj, rev, ret1*adjInst, spendMetaVND, instMeta]
    j_dcregeo = json.dumps({cid: {g: {dy: [a[0], jnum(a[1]), jnum(a[2]), jnum(a[3]), jnum(a[4]), a[5]] for dy, a in dd.items()}
                                  for g, dd in geos.items()} for cid, geos in DCREGEO.items()}, ensure_ascii=False)
    # campaign×country: [adjInst, costAdj, rev, ret1*adjInst, spendMetaVND, instMeta]
    j_dcamgeo = json.dumps({c: {g: {dy: [a[0], jnum(a[1]), jnum(a[2]), jnum(a[4]), jnum(a[5]), a[6]] for dy, a in dd.items()}
                                for g, dd in geos.items()} for c, geos in DCAMGEO.items()}, ensure_ascii=False)
    j_angn = json.dumps(ang_name)
    j_angre = json.dumps(r"^SAYA_(S\d+)" if is_saya else r"^CAR_(A\d+)")
    j_qr = json.dumps(QR)
    # Ngưỡng màu CPI theo app: Cardia (India/EN, CPI thấp) vs Saya (global mix, CPI cao hơn)
    j_cpit = json.dumps([0.5, 1.5] if is_saya else [0.12, 0.3])

    APP = """
    const ALLDAYS = __DAYS__, DTOT = __DTOT__, DGEO = __DGEO__, DCRE = __DCRE__, DCAM = __DCAM__, CAM_OBJ = __COBJ__, CAM_STATUS = __CSTAT__, DACAM_ADJ = __DACADJ__, CAM_CH = __CAMCH__, DCREGEO = __DCREGEO__, DCAMGEO = __DCAMGEO__, ANGN = __ANGN__, QR = __QR__, FX = __FX__, D1CUT = __D1CUT__, CPI_T = __CPIT__;
    const GREEN='#0f9d6b', RED='#d6454f';
    function DT(d){ return DTOT[d] || [0,0,0,0,0]; }

    // ---------- khung thời gian ----------
    function daysFor(w){
      const n=ALLDAYS.length;
      if(w==='today') return ALLDAYS.slice(n-1);
      if(w==='yesterday') return ALLDAYS.slice(n-2,n-1);
      if(w==='all') return ALLDAYS.slice();
      const k=parseInt(w,10); return ALLDAYS.slice(Math.max(0,n-k));
    }
    function prevFor(w){
      const n=ALLDAYS.length;
      if(w==='today') return ALLDAYS.slice(n-2,n-1);
      if(w==='yesterday') return ALLDAYS.slice(n-3,n-2);
      if(w==='all') return [];
      const k=parseInt(w,10); const end=Math.max(0,n-k); return ALLDAYS.slice(Math.max(0,end-k),end);
    }
    function totals(days){
      let inst=0,cost=0,rev=0,r1=0,r7c=0;
      days.forEach(function(d){ const a=DT(d); inst+=a[0];cost+=a[1];rev+=a[2];r7c+=a[3];r1+=a[4]; });
      return {inst:inst,cost:cost,rev:rev,cpi:inst?cost/inst:0,roas:cost?rev/cost:0,
              ltv:inst?rev/inst:0,d1:inst?r1/inst*100:0,roasd7:cost?r7c/cost:0};
    }
    const DAYVAL = {
      installs:function(d){return DT(d)[0];},
      spend:function(d){return DT(d)[1];},
      revenue:function(d){return DT(d)[2];},
      cpi:function(d){return DT(d)[0]?DT(d)[1]/DT(d)[0]:0;},
      roas:function(d){return DT(d)[1]?DT(d)[2]/DT(d)[1]:0;},
      d1:function(d){return DT(d)[0]?DT(d)[4]/DT(d)[0]*100:0;},
      roasd7:function(d){return DT(d)[1]?DT(d)[3]/DT(d)[1]:0;}
    };

    // ---------- format ----------
    function fmtInt(v){ return Math.abs(v)>=1000?(v/1000).toFixed(1)+'K':Math.round(v).toLocaleString(); }
    function fmtUSD(v){ return '$'+(Math.abs(v)>=10000?(v/1000).toFixed(1)+'K':v.toFixed(2)); }
    const KPIS = [
      {k:'installs',label:'Installs',up:true, val:t=>t.inst, fmt:fmtInt, spark:GREEN},
      {k:'spend',   label:'Spend',   up:true, val:t=>t.cost, fmt:fmtUSD, spark:GREEN},
      {k:'revenue', label:'Revenue', up:true, val:t=>t.rev,  fmt:fmtUSD, spark:GREEN},
      {k:'cpi',     label:'CPI',     up:false,val:t=>t.cpi,  fmt:v=>'$'+v.toFixed(3), spark:RED,
        status:v=>v<CPI_T[0]?'good':v<CPI_T[1]?'warn':'bad'},
      {k:'roas',    label:'ROAS (cum)',up:true,val:t=>t.roas,fmt:v=>v.toFixed(2)+'x', spark:GREEN,
        status:v=>v>=1?'good':v>=0.5?'warn':'bad'},
      {k:'d1',      label:'D1 retention',up:true,val:t=>t.d1,fmt:v=>v.toFixed(1)+'%', spark:GREEN,
        status:v=>v>=10?'good':v>=6?'warn':'bad'},
      {k:'roasd7',  label:'ROAS D7',up:true, val:t=>t.roasd7,fmt:v=>v.toFixed(2)+'x', spark:GREEN,
        status:v=>v>=1?'good':v>=0.5?'warn':'bad'}
    ];

    // ---------- làm mượt đường ----------
    function smooth(p){
      if(p.length<2) return p.length?('M'+p[0].x+' '+p[0].y):'';
      let d='M'+p[0].x.toFixed(1)+' '+p[0].y.toFixed(1);
      for(let i=0;i<p.length-1;i++){
        const p0=p[i-1]||p[i],p1=p[i],p2=p[i+1],p3=p[i+2]||p2;
        d+=' C'+(p1.x+(p2.x-p0.x)/6).toFixed(1)+' '+(p1.y+(p2.y-p0.y)/6).toFixed(1)
          +' '+(p2.x-(p3.x-p1.x)/6).toFixed(1)+' '+(p2.y-(p3.y-p1.y)/6).toFixed(1)
          +' '+p2.x.toFixed(1)+' '+p2.y.toFixed(1);
      }
      return d;
    }
    // cột bo góc TRÊN (đáy vuông) — trông mềm như chart hiện đại
    function barPath(x,y,w,h){
      if(h<=0.4) return '';
      const r=Math.min(w/2,3.5,h);
      return 'M'+x.toFixed(1)+' '+(y+h).toFixed(1)
        +' L'+x.toFixed(1)+' '+(y+r).toFixed(1)
        +' Q'+x.toFixed(1)+' '+y.toFixed(1)+' '+(x+r).toFixed(1)+' '+y.toFixed(1)
        +' L'+(x+w-r).toFixed(1)+' '+y.toFixed(1)
        +' Q'+(x+w).toFixed(1)+' '+y.toFixed(1)+' '+(x+w).toFixed(1)+' '+(y+r).toFixed(1)
        +' L'+(x+w).toFixed(1)+' '+(y+h).toFixed(1)+' Z';
    }
    function spark(vals,color){
      const n=vals.length; if(!n) return '';
      const mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
      const pts=vals.map(function(v,i){return {x:n<=1?50:i/(n-1)*100,y:30-((v-mn)/rng*26)};});
      const line=smooth(pts), area=line+' L100 34 L0 34 Z';
      return '<svg class="spark" viewBox="0 0 100 34" preserveAspectRatio="none">'
        +'<path d="'+area+'" fill="'+color+'" opacity="0.13"/>'
        +'<path d="'+line+'" fill="none" stroke="'+color+'" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>';
    }
    function deltaParts(cur,prev,upGood){
      if(prev===0||prev==null||!isFinite(prev)) return {cls:'flat',txt:'—'};
      const ch=(cur-prev)/Math.abs(prev)*100, up=ch>=0;
      if(Math.abs(ch)<0.05) return {cls:'flat',txt:'→ 0%'};
      return {cls:(up===upGood)?'up':'down', txt:(up?'▲ ':'▼ ')+Math.abs(ch).toFixed(1)+'%'};
    }

    // ---------- render KPI ----------
    function renderKPIs(days,prevdays){
      const T=totals(days), P=totals(prevdays);
      document.getElementById('grid').innerHTML = KPIS.map(function(kp){
        const v=kp.val(T), pv=kp.val(P), st=kp.status?kp.status(v):'';
        const dl=deltaParts(v,pv,kp.up);
        const series=days.map(DAYVAL[kp.k]);
        return '<div class="kpi '+st+'">'
          +'<div class="kpi-l">'+kp.label+'</div>'
          +'<div class="kpi-v">'+kp.fmt(v)+'</div>'
          +'<div class="kpi-delta '+dl.cls+'">'+dl.txt+' <span class="vs">vs prev.</span></div>'
          +spark(series, kp.spark)
          +'</div>';
      }).join('');
    }

    // ---------- biểu đồ lớn (combo bar + line, 2 trục) ----------
    let curMetric='install', PTS=[], GEOM=null, CHARTDATA=null;
    const usd0=v=>'$'+(Math.abs(v)>=1000?(v/1000).toFixed(1)+'K':v.toFixed(0));
    const usd2=v=>'$'+v.toFixed(2);
    const CHARTS = {
      install:{ aria:'Install & CPI', leftTitle:'Install', rightTitle:'CPI',
        bars:[{k:'installs', color:'#4f7df6', name:'Install', fmt:fmtInt}],
        line:{k:'cpi', color:'#8b5cf6', name:'CPI', fmt:v=>'$'+v.toFixed(3)},
        leftFmt:fmtInt, rightFmt:v=>'$'+v.toFixed(2) },
      roas:{ aria:'Spend, Revenue & ROAS', leftTitle:'USD', rightTitle:'ROAS',
        bars:[{k:'spend', color:'#4f7df6', name:'Spend', fmt:usd2},
              {k:'revenue', color:'#0f9d6b', name:'Revenue', fmt:usd2}],
        line:{k:'roas', color:'#8b5cf6', name:'ROAS', fmt:v=>v.toFixed(2)+'x'},
        leftFmt:usd0, rightFmt:v=>v.toFixed(2)+'x' }
    };
    function renderChart(m,days){
      curMetric=m;
      const cfg=CHARTS[m]||CHARTS.install;
      const wrap=document.getElementById('chartwrap');
      const W=Math.max(wrap.clientWidth||640,320), H=280, L=52,R=52,T=30,B=30, pw=W-L-R, ph=H-T-B;
      const n=days.length, band=n?pw/n:pw, base=T+ph;
      const barSeries=cfg.bars.map(function(b){ return days.map(DAYVAL[b.k]); });
      const lineVals=days.map(DAYVAL[cfg.line.k]);
      const mxL=Math.max.apply(null,[].concat.apply([],barSeries).concat([0.0001]))*1.12;
      const mxR=Math.max.apply(null,lineVals.concat([0.0001]))*1.12;
      const cx=i=> L+(i+0.5)*band, yL=v=> T+(1-v/mxL)*ph, yR=v=> T+(1-v/mxR)*ph;
      const lc=cfg.line.color;
      let grid='';
      for(let g=0;g<=4;g++){ const yy=T+ph*g/4;
        grid+='<line class="gridline" x1="'+L+'" y1="'+yy.toFixed(1)+'" x2="'+(W-R)+'" y2="'+yy.toFixed(1)+'"/>';
        grid+='<text class="axislbl" x="'+(L-9)+'" y="'+(yy+3.7).toFixed(1)+'" text-anchor="end">'+cfg.leftFmt(mxL*(1-g/4))+'</text>';
        grid+='<text class="axislbl" x="'+(W-R+9)+'" y="'+(yy+3.7).toFixed(1)+'" text-anchor="start">'+cfg.rightFmt(mxR*(1-g/4))+'</text>'; }
      let xl='', step=Math.max(1,Math.ceil(n/12));
      for(let i=0;i<n;i++){ if(i%step===0||i===n-1) xl+='<text id="xlbl_'+i+'" class="axislbl xlbl" x="'+cx(i).toFixed(1)+'" y="'+(H-10)+'" text-anchor="middle">'+days[i].slice(5).replace('-','/')+'</text>'; }
      // gradient defs
      let defs='<defs>';
      cfg.bars.forEach(function(b,s){ defs+='<linearGradient id="bg_'+m+'_'+s+'" x1="0" x2="0" y1="0" y2="1">'
        +'<stop offset="0" stop-color="'+b.color+'" stop-opacity="0.95"/>'
        +'<stop offset="1" stop-color="'+b.color+'" stop-opacity="0.30"/></linearGradient>'; });
      defs+='<linearGradient id="ar_'+m+'" x1="0" x2="0" y1="0" y2="1">'
        +'<stop offset="0" stop-color="'+lc+'" stop-opacity="0.16"/>'
        +'<stop offset="1" stop-color="'+lc+'" stop-opacity="0"/></linearGradient></defs>';
      // cột (gradient + bo góc trên)
      const nb=cfg.bars.length, bw=nb>1?Math.max(2.5,band*0.27):Math.max(3,band*0.46);
      let bars='';
      for(let i=0;i<n;i++){ for(let s=0;s<nb;s++){ const v=barSeries[s][i]; if(!(v>0)) continue;
        const bx=nb>1?(cx(i)-bw-1.5+s*(bw+3)):(cx(i)-bw/2), by=yL(v);
        bars+='<path d="'+barPath(bx,by,bw,base-by)+'" fill="url(#bg_'+m+'_'+s+')"/>'; } }
      PTS=lineVals.map(function(v,i){return {x:cx(i),y:yR(v),v:v,d:days[i]};});
      GEOM={W:W,L:L,R:R,T:T,ph:ph,base:base,pw:pw,n:n,band:band,mxL:mxL}; CHARTDATA={cfg:cfg,bars:barSeries,lineVals:lineVals};
      const line=smooth(PTS), area=n?line+' L'+PTS[n-1].x.toFixed(1)+' '+base.toFixed(1)+' L'+PTS[0].x.toFixed(1)+' '+base.toFixed(1)+' Z':'';
      const mr=n<=10?3.6:n<=18?2.6:2;  // marker nhỏ dần khi nhiều điểm — giữ ở MỌI khung
      let marks=''; PTS.forEach(function(p){ marks+='<circle cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="'+mr+'" fill="#fff" stroke="'+lc+'" stroke-width="'+(n<=18?2:1.6)+'"/>'; });
      document.getElementById('svghost').innerHTML='<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+cfg.aria+'">'
        +defs+grid
        +'<rect id="hband" class="hband" x="0" y="'+T+'" width="0" height="'+ph.toFixed(1)+'" rx="6" style="display:none"/>'
        +'<text class="axisttl" x="'+L+'" y="15" text-anchor="start">'+cfg.leftTitle+'</text>'
        +'<text class="axisttl" x="'+(W-R)+'" y="15" text-anchor="end">'+cfg.rightTitle+'</text>'
        +bars
        +'<path d="'+area+'" fill="url(#ar_'+m+')"/>'
        +'<path d="'+line+'" fill="none" stroke="'+lc+'" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
        +marks
        +'<line id="hcross" class="hcross" x1="'+L+'" x2="'+(W-R)+'" y1="0" y2="0" style="display:none"/>'
        +'<g id="lpill" class="vpill" style="display:none"><rect rx="5" height="18"></rect><text></text></g>'
        +'<g id="rpill" class="vpill" style="display:none"><rect rx="5" height="18"></rect><text></text></g>'
        +'<g id="xpill" class="xpill" style="display:none"><rect rx="6" height="20"></rect><text></text></g>'
        +'<circle id="dot" r="5" fill="#fff" stroke="'+lc+'" stroke-width="3" style="display:none"/>'
        +xl+'<rect id="ov" x="'+L+'" y="'+T+'" width="'+pw+'" height="'+ph+'" fill="transparent" style="cursor:crosshair"/></svg>';
      const lg=document.getElementById('chartlegend');
      if(lg) lg.innerHTML=cfg.bars.map(function(b){return '<i><span class="sw" style="background:'+b.color+'"></span>'+b.name+'</i>';}).join('')
        +'<i><span class="swl" style="border-color:'+lc+'"></span>'+cfg.line.name+'</i>';
      bindHover();
    }
    function setPill(g,cxp,cyp,txt,anchorRight){
      const rect=g.firstChild, t=rect.nextSibling, w=txt.length*6.6+16;
      t.textContent=txt;
      const rx = anchorRight ? (cxp+4) : (cxp-4-w);
      rect.setAttribute('x',rx.toFixed(1)); rect.setAttribute('y',(cyp-9).toFixed(1)); rect.setAttribute('width',w.toFixed(1));
      t.setAttribute('x',(rx+w/2).toFixed(1)); t.setAttribute('y',(cyp+3.6).toFixed(1)); t.setAttribute('text-anchor','middle');
      g.style.display='';
    }
    function bindHover(){
      const host=document.getElementById('svghost'),ov=document.getElementById('ov');
      const hband=document.getElementById('hband'),hcross=document.getElementById('hcross'),dot=document.getElementById('dot'),tip=document.getElementById('tip');
      const lpill=document.getElementById('lpill'),rpill=document.getElementById('rpill'),xpill=document.getElementById('xpill');
      if(!ov) return;
      let hiddenLbl=null;  // nhãn ngày tĩnh đang bị ẩn (để pill hover thay thế, tránh đè chữ)
      function showLbl(){ if(hiddenLbl){ hiddenLbl.style.visibility=''; hiddenLbl=null; } }
      function hide(){ [hband,hcross,dot,lpill,rpill,xpill].forEach(function(e){e.style.display='none';}); tip.hidden=true; showLbl(); }
      ov.addEventListener('mousemove',function(e){
        const r=host.getBoundingClientRect(),scale=r.width/GEOM.W,px=(e.clientX-r.left)/scale;
        let i=Math.floor((px-GEOM.L)/GEOM.band); i=Math.max(0,Math.min(GEOM.n-1,i));
        const lbl=document.getElementById('xlbl_'+i);
        if(lbl!==hiddenLbl){ showLbl(); if(lbl){ lbl.style.visibility='hidden'; hiddenLbl=lbl; } }
        const p=PTS[i], cfg=CHARTDATA.cfg, bw=GEOM.band*0.8;
        hband.setAttribute('x',(p.x-bw/2).toFixed(1)); hband.setAttribute('width',bw.toFixed(1)); hband.style.display='';
        hcross.setAttribute('y1',p.y.toFixed(1)); hcross.setAttribute('y2',p.y.toFixed(1)); hcross.style.display='';
        dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);dot.style.display='';
        // pill giá trị 2 trục tại độ cao điểm hover
        const valL=GEOM.mxL*(1-(p.y-GEOM.T)/GEOM.ph);
        setPill(lpill,GEOM.L,p.y,cfg.leftFmt(valL),false);
        setPill(rpill,GEOM.W-GEOM.R,p.y,cfg.rightFmt(p.v),true);
        // pill nhãn ngày dưới trục X
        setPill(xpill,p.x,GEOM.base+15,p.d.slice(5).replace('-','/'),'mid');
        const xr=xpill.firstChild, xt=xr.nextSibling, xw=parseFloat(xr.getAttribute('width'));
        xr.setAttribute('x',(p.x-xw/2).toFixed(1)); xt.setAttribute('x',p.x.toFixed(1));
        let html='<div class="d">'+p.d+'</div>';
        cfg.bars.forEach(function(b,s){ html+='<div class="vrow"><span class="dotc" style="background:'+b.color+'"></span>'+b.name+': <b>'+b.fmt(CHARTDATA.bars[s][i])+'</b></div>'; });
        html+='<div class="vrow"><span class="dotc" style="background:'+cfg.line.color+'"></span>'+cfg.line.name+': <b>'+cfg.line.fmt(CHARTDATA.lineVals[i])+'</b></div>';
        tip.hidden=false; tip.innerHTML=html;
        tip.style.left=Math.max(70,Math.min(r.width-70,p.x*scale))+'px'; tip.style.top=Math.max(8,(p.y*scale)-12)+'px';
      });
      ov.addEventListener('mouseleave',hide);
    }

    // ---------- bảng geo / creative ----------
    const GEO3={'India':'IND','Africa':'AFR','LATAM':'LAT','Pakistan':'PAK','South Asia':'SAS','SEA':'SEA','Middle East':'MEA','US':'USA','United States':'USA','Oceania':'OCE','Brazil':'BRA','Central Asia':'CAS','East Asia':'EAS','North America':'NAM','Europe':'EUR','Cayman Islands':'CYM','Sint Maarten':'SXM','Virgin Islands (US)':'VIR','Guadeloupe':'GLP','Martinique':'MTQ','Saint Martin':'MAF','Falkland Islands':'FLK','Northern Mariana Islands':'MNP'};
    function code3(n){ if(n.indexOf('Other')===0) return 'OTH'; if(GEO3[n]) return GEO3[n]; return n.replace(/[^A-Za-z]/g,'').slice(0,3).toUpperCase(); }
    // ramp 1 màu xanh lá (cùng tông cột Revenue #0f9d6b): top1 đậm nhất → nhỏ dần nhạt dần
    function geoShade(i,n){ const t=n<=1?0:i/(n-1); const L=Math.round(30+t*52), S=Math.round(78-t*38);
      return {fill:'hsl(159,'+S+'%,'+L+'%)', txt: L>=60?'var(--txt)':'#fff'}; }
    function geoCells(x){
      const cpi=x.inst?x.cost/x.inst:0,roas=x.cost?x.rev/x.cost:0,rd7=x.cost?x.r7c/x.cost:0,ltv=x.inst?x.rev/x.inst:0;
      const cc=cpi<CPI_T[0]?'good':cpi<CPI_T[1]?'warn':'bad';
      const hasD1=x.matI>0, d1=hasD1?x.r1m/x.matI*100:0;   // chỉ tính D1 trên cohort đã chín
      const dc=!hasD1?'':(d1>6?'good':d1>3?'warn':'bad');
      const d1cell=hasD1?d1.toFixed(1):'<span class="adjf" title="Cohort chưa đủ chín để đo D1 (install < 2 ngày so với data mới nhất) — chưa có số, không phải 0%">–</span>';
      return '<td>'+x.inst.toLocaleString()+'</td><td>$'+x.cost.toFixed(2)+'</td><td>$'+x.rev.toFixed(2)+'</td><td class="'+cc+'">$'+cpi.toFixed(3)+'</td><td>$'+ltv.toFixed(3)+'</td><td>'+roas.toFixed(2)+'x</td><td class="'+dc+'">'+d1cell+'</td><td>'+rd7.toFixed(2)+'x</td>';
    }
    function buildDonut(slices,totalInst){
      const sum=slices.reduce(function(s,x){return s+x.value;},0);
      if(!sum) return '<div class="pie-empty">Chưa có install trong khung thời gian này</div>';
      const cx=190,cy=190,R=178,ri=112,rmid=(R+ri)/2,THRESH=0.04; let a0=-Math.PI/2, paths='', labels='';
      slices.forEach(function(s){
        const frac=s.value/sum, a1=a0+frac*2*Math.PI, mid=(a0+a1)/2, pct=(frac*100).toFixed(1);
        const data='data-lbl="'+s.label+'" data-inst="'+s.value.toLocaleString()+'" data-pct="'+pct+'" data-rev="$'+s.rev.toFixed(2)+'" data-roas="'+s.roas.toFixed(2)+'x" data-color="'+s.color+'"';
        if(frac>=0.99999){
          paths+='<circle cx="'+cx+'" cy="'+cy+'" r="'+rmid+'" fill="none" stroke="'+s.color+'" stroke-width="'+(R-ri)+'" class="pieslice" '+data+'></circle>';
        } else {
          const large=(a1-a0)>Math.PI?1:0;
          const x0=cx+R*Math.cos(a0),y0=cy+R*Math.sin(a0),x1=cx+R*Math.cos(a1),y1=cy+R*Math.sin(a1);
          const xi1=cx+ri*Math.cos(a1),yi1=cy+ri*Math.sin(a1),xi0=cx+ri*Math.cos(a0),yi0=cy+ri*Math.sin(a0);
          const d='M'+x0+' '+y0+' A'+R+' '+R+' 0 '+large+' 1 '+x1+' '+y1+' L'+xi1+' '+yi1+' A'+ri+' '+ri+' 0 '+large+' 0 '+xi0+' '+yi0+' Z';
          paths+='<path class="pieslice" d="'+d+'" fill="'+s.color+'" '+data+'></path>';
        }
        if(frac>=THRESH){
          const lx=cx+rmid*Math.cos(mid),ly=cy+rmid*Math.sin(mid);
          labels+='<text class="pie-in-name" x="'+lx.toFixed(1)+'" y="'+(ly-3).toFixed(1)+'" text-anchor="middle" fill="'+s.txt+'">'+code3(s.label)+'</text>';
          labels+='<text class="pie-in-pct" x="'+lx.toFixed(1)+'" y="'+(ly+12).toFixed(1)+'" text-anchor="middle" fill="'+s.txt+'">'+pct+'%</text>';
        }
        a0=a1;
      });
      const svg='<svg viewBox="0 0 380 380" class="donut" role="img" aria-label="Tỷ trọng install theo quốc gia">'
        +paths+labels
        +'<text x="'+cx+'" y="'+(cy-6)+'" class="donut-num" text-anchor="middle">'+totalInst.toLocaleString()+'</text>'
        +'<text x="'+cx+'" y="'+(cy+20)+'" class="donut-lbl" text-anchor="middle">installs</text></svg>';
      return '<div class="pie-graphic">'+svg+'</div>';
    }
    function showGeoTip(p,cx,cy){
      const tip=document.getElementById('geoTip'); if(!tip||!p||!p.dataset) return;
      tip.innerHTML='<div class="gt-h"><span class="gt-dot" style="background:'+p.dataset.color+'"></span>'+p.dataset.lbl+'</div>'
        +'<div class="gt-row"><span>Install</span><b>'+p.dataset.inst+'</b></div>'
        +'<div class="gt-row"><span>Share</span><b>'+p.dataset.pct+'%</b></div>'
        +'<div class="gt-row"><span>Revenue</span><b>'+p.dataset.rev+'</b></div>'
        +'<div class="gt-row"><span>ROAS</span><b>'+p.dataset.roas+'</b></div>';
      tip.hidden=false;
      let x=cx+16, y=cy+16; const w=tip.offsetWidth, h=tip.offsetHeight;
      if(x+w>window.innerWidth-8) x=cx-w-16;
      if(y+h>window.innerHeight-8) y=cy-h-16;
      if(x<8) x=8; if(y<8) y=8;
      tip.style.left=x+'px'; tip.style.top=y+'px';
    }
    function hideGeoTip(){ const tip=document.getElementById('geoTip'); if(tip) tip.hidden=true; }
    function renderGeo(days){
      const all=Object.keys(DGEO).map(function(g){
        let inst=0,cost=0,rev=0,r1=0,r7c=0,matI=0,r1m=0;
        days.forEach(function(d){ const a=DGEO[g][d]; if(a){inst+=a[0];cost+=a[1];rev+=a[2];r7c+=a[3];r1+=a[4]; if(d<=D1CUT){matI+=a[0];r1m+=a[4];}} });
        return {g:g,inst:inst,cost:cost,rev:rev,r1:r1,r7c:r7c,matI:matI,r1m:r1m};
      }).filter(function(x){return x.inst>0||x.cost>0;}).sort(function(a,b){return b.inst-a.inst;});
      if(!all.length){
        document.getElementById('geoBody').innerHTML='<tr><td colspan="9" style="text-align:center;color:var(--mut)">không có data trong khung thời gian này</td></tr>';
        document.getElementById('geoPie').innerHTML='<div class="pie-empty">Chưa có install trong khung thời gian này</div>';
        return;
      }
      const top=all.slice(0,10), rest=all.slice(10);
      const other=rest.reduce(function(s,x){s.inst+=x.inst;s.cost+=x.cost;s.rev+=x.rev;s.r1+=x.r1;s.r7c+=x.r7c;s.matI+=x.matI;s.r1m+=x.r1m;return s;},{inst:0,cost:0,rev:0,r1:0,r7c:0,matI:0,r1m:0});
      const total=all.reduce(function(s,x){s.inst+=x.inst;s.cost+=x.cost;s.rev+=x.rev;s.r1+=x.r1;s.r7c+=x.r7c;s.matI+=x.matI;s.r1m+=x.r1m;return s;},{inst:0,cost:0,rev:0,r1:0,r7c:0,matI:0,r1m:0});
      // ---- bảng: top 10 theo Install + Other + Total ----
      let html=top.map(function(x,i){ return '<tr'+(i%2?' class="zeb"':'')+'><td>'+x.g+'</td>'+geoCells(x)+'</tr>'; }).join('');
      if(rest.length) html+='<tr class="geo-other'+(top.length%2?' zeb':'')+'"><td>Other ('+rest.length+')</td>'+geoCells(other)+'</tr>';
      html+='<tr class="trow-tot"><td>Total</td>'+geoCells(total)+'</tr>';
      document.getElementById('geoBody').innerHTML=html;
      // ---- donut: tỷ trọng install (top 10 + Other) ----
      const pieSrc=top.filter(function(x){return x.inst>0;}).map(function(x){return {label:x.g,value:x.inst,rev:x.rev,roas:x.cost?x.rev/x.cost:0};});
      if(rest.length && other.inst>0) pieSrc.push({label:'Other ('+rest.length+')',value:other.inst,rev:other.rev,roas:other.cost?other.rev/other.cost:0});
      const slices=pieSrc.map(function(s,i){ const sh=geoShade(i,pieSrc.length); s.color=sh.fill; s.txt=sh.txt; return s; });
      const pie=document.getElementById('geoPie');
      pie.innerHTML=buildDonut(slices,total.inst);
      // hover (desktop) 1 country → popup chi tiết (Install / Revenue / ROAS); center giữ nguyên tổng
      pie.querySelectorAll('.pieslice').forEach(function(p){
        p.addEventListener('mouseenter',function(e){ showGeoTip(p,e.clientX,e.clientY); });
        p.addEventListener('mousemove',function(e){ showGeoTip(p,e.clientX,e.clientY); });
        p.addEventListener('mouseleave',hideGeoTip);
      });
    }
    function renderCre(days){
      if(!document.getElementById('creBody')) return;
      const rows=Object.keys(DCRE).map(function(c){
        let sp=0,impr=0,lc=0,inst=0,v3=0;
        days.forEach(function(d){ const a=DCRE[c][d]; if(a){sp+=a[0];impr+=a[1];lc+=a[2];inst+=a[3];v3+=a[4];} });
        return {c:c,sp:sp,impr:impr,lc:lc,inst:inst,v3:v3};
      }).filter(function(x){return x.impr>0;}).sort(function(a,b){return b.impr-a.impr;});
      document.getElementById('creBody').innerHTML = rows.length? rows.map(function(x,i){
        const cpi=x.inst?(x.sp/FX)/x.inst:0,ctr=x.impr?x.lc/x.impr*100:0,cvr=x.lc?x.inst/x.lc*100:0,hook=x.impr?x.v3/x.impr*100:0;
        const q=QR[x.c]||'',qc=/BELOW/.test(q)?'bad':(q==='AVERAGE'||q==='ABOVE_AVERAGE'?'good':'mut'),cc=ctr>6?'good':ctr>3?'warn':'bad';
        const exp=DCREGEO[x.c]?' expandable':'', car=DCREGEO[x.c]?'<span class="caret">▸</span> ':'';
        return '<tr class="crow'+exp+(i%2?' zeb':'')+'" data-cid="'+x.c+'"><td class="mono">'+car+x.c+'</td><td class="angcell">'+angOf(x.c)+'</td><td>'+x.impr.toLocaleString()+'</td><td>'+x.inst.toLocaleString()+'</td><td>$'+cpi.toFixed(3)+'</td><td class="'+cc+'">'+ctr.toFixed(2)+'%</td><td>'+cvr.toFixed(1)+'%</td><td>'+hook.toFixed(1)+'%</td><td class="'+qc+'" title="'+(q||'chưa có dữ liệu')+'">'+qLabel(q)+'</td></tr>';
      }).join('')+(function(){
        var T=rows.reduce(function(s,x){s.sp+=x.sp;s.impr+=x.impr;s.lc+=x.lc;s.inst+=x.inst;s.v3+=x.v3;return s;},{sp:0,impr:0,lc:0,inst:0,v3:0});
        var cpi=T.inst?(T.sp/FX)/T.inst:0,ctr=T.impr?T.lc/T.impr*100:0,cvr=T.lc?T.inst/T.lc*100:0,hook=T.impr?T.v3/T.impr*100:0;
        return '<tr class="trow-tot"><td>Total</td><td></td><td>'+T.impr.toLocaleString()+'</td><td>'+T.inst.toLocaleString()+'</td><td>$'+cpi.toFixed(3)+'</td><td>'+ctr.toFixed(2)+'%</td><td>'+cvr.toFixed(1)+'%</td><td>'+hook.toFixed(1)+'%</td><td>—</td></tr>';
      })() : '<tr><td colspan="9" style="text-align:center;color:var(--mut)">không có data trong khung thời gian này</td></tr>';
    }
    // breakdown creative theo country. a=[adjInst, costAdj, rev, ret1*adjInst, spendMetaVND, instMeta]
    // Inst/Spend/CPI = Meta (khớp hàng cha). Rev/LTV/ROAS: Adjust rev ÷ spend Meta. D1 = Adjust, chỉ cohort chín (d<=D1CUT) → nếu chưa chín hiện "–".
    function creGeoSub(cid,days){
      const g=DCREGEO[cid]; if(!g) return '';
      const rows=Object.keys(g).map(function(geo){
        let ainst=0,acost=0,rev=0,msp=0,minst=0,matInst=0,r1m=0;
        days.forEach(function(d){ const a=g[geo][d]; if(a){
          ainst+=a[0];acost+=a[1];rev+=a[2];msp+=(a[4]||0);minst+=(a[5]||0);
          if(d<=D1CUT){ matInst+=a[0]; r1m+=a[3]; }
        } });
        const mcost=msp/FX, useM=mcost>0;
        const cost=useM?mcost:acost;
        const inst=useM?minst:ainst;
        return {geo:geo,inst:inst,cost:cost,rev:rev,matInst:matInst,r1m:r1m,useM:useM};
      }).filter(function(x){return x.inst>0||x.cost>0.01;}).sort(function(a,b){return b.cost-a.cost;});
      if(!rows.length) return '<div class="subempty">Không có dữ liệu theo country trong khung thời gian này.</div>';
      return '<div class="subwrap">'
        +'<table class="subt"><thead><tr><th>Country</th><th>Inst</th><th>Spend</th><th>CPI</th><th>Rev</th><th>LTV</th><th>ROAS</th><th>D1</th></tr></thead><tbody>'
        +rows.map(function(x,i){ const cpi=x.inst?x.cost/x.inst:0,roas=x.cost?x.rev/x.cost:0,ltv=x.inst?x.rev/x.inst:0;
          const cc=cpi<CPI_T[0]?'good':cpi<CPI_T[1]?'warn':'bad';
          const d1=x.matInst>0?(x.r1m/x.matInst*100).toFixed(1):'<span class="adjf" title="Cohort chưa đủ chín để đo D1 (install < 2 ngày) hoặc chưa có install Adjust — chưa có số, không phải 0%">–</span>';
          const flag=x.useM?'':'<span class="adjf" title="Meta không tách spend cho country này — đang dùng Adjust cost (thường thiếu)">~adj</span>';
          return '<tr'+(i>=10?' class="cty-x"':'')+'><td>'+x.geo+'</td><td>'+x.inst.toLocaleString()+'</td><td>$'+x.cost.toFixed(2)+flag+'</td><td class="'+cc+'">$'+cpi.toFixed(3)+'</td><td>$'+x.rev.toFixed(2)+'</td><td>$'+ltv.toFixed(3)+'</td><td>'+roas.toFixed(2)+'x</td><td>'+d1+'</td></tr>';
        }).join('')+'</tbody></table>'+moreBtn(rows.length-10)+'</div>';
    }
    // top 10 country mặc định + nút bung full (dùng chung cho campaign & creative sub-table)
    function toggleCty(btn){ const w=btn.closest('.subwrap'); const on=w.classList.toggle('allc');
      btn.textContent = on ? 'Show less ▴' : ('Show '+btn.dataset.n+' more ▾'); }
    function moreBtn(n){ return n>0 ? '<button class="morebtn" data-n="'+n+'" onclick="toggleCty(this)">Show '+n+' more ▾</button>' : ''; }
    // breakdown campaign theo country. a=[adjInst, costAdj, rev, ret1*adjInst, spendMetaVND, instMeta]
    // Inst/Spend/CPI = Meta (khớp hàng cha). Rev/LTV/ROAS dùng Adjust rev ÷ spend Meta.
    // D1 = Adjust, chỉ tính trên install-day đã CHÍN (d<=D1CUT); cohort chưa chín → "–" (không phải 0%).
    function camGeoSub(cam,days){
      const g=DCAMGEO[cam]; if(!g) return '';
      const rows=Object.keys(g).map(function(geo){
        let ainst=0,acost=0,rev=0,msp=0,minst=0,matInst=0,r1m=0;
        days.forEach(function(d){ const a=g[geo][d]; if(a){
          ainst+=a[0];acost+=a[1];rev+=a[2];msp+=(a[4]||0);minst+=(a[5]||0);
          if(d<=D1CUT){ matInst+=a[0]; r1m+=a[3]; }   // chỉ cohort đã chín mới tính D1
        } });
        const mcost=msp/FX, useM=mcost>0;
        const cost=useM?mcost:acost;          // ưu tiên spend Meta, fallback Adjust cost
        const inst=useM?minst:ainst;          // ưu tiên install Meta (khớp hàng cha), fallback Adjust
        return {geo:geo,inst:inst,cost:cost,rev:rev,matInst:matInst,r1m:r1m,useM:useM};
      }).filter(function(x){return x.inst>0||x.cost>0.01;}).sort(function(a,b){return b.cost-a.cost;});
      if(!rows.length) return '<div class="subempty">Không có dữ liệu theo country trong khung thời gian này.</div>';
      return '<div class="subwrap">'
        +'<table class="subt"><thead><tr><th>Country</th><th>Inst</th><th>Spend</th><th>CPI</th><th>Rev</th><th>LTV</th><th>ROAS</th><th>D1</th></tr></thead><tbody>'
        +rows.map(function(x,i){ const cpi=x.inst?x.cost/x.inst:0,roas=x.cost?x.rev/x.cost:0,ltv=x.inst?x.rev/x.inst:0;
          const cc=cpi<CPI_T[0]?'good':cpi<CPI_T[1]?'warn':'bad';
          const d1=x.matInst>0?(x.r1m/x.matInst*100).toFixed(1):'<span class="adjf" title="Cohort chưa đủ chín để đo D1 (install < 2 ngày) hoặc chưa có install Adjust — chưa có số, không phải 0%">–</span>';
          const flag=x.useM?'':'<span class="adjf" title="Meta không tách spend cho geo này — đang dùng Adjust cost (thường thiếu)">~adj</span>';
          return '<tr'+(i>=10?' class="cty-x"':'')+'><td>'+x.geo+'</td><td>'+x.inst.toLocaleString()+'</td><td>$'+x.cost.toFixed(2)+flag+'</td><td class="'+cc+'">$'+cpi.toFixed(3)+'</td><td>$'+x.rev.toFixed(2)+'</td><td>$'+ltv.toFixed(3)+'</td><td>'+roas.toFixed(2)+'x</td><td>'+d1+'</td></tr>';
        }).join('')+'</tbody></table>'+moreBtn(rows.length-10)+'</div>';
    }
    function statHtml(cam){
      const s=(CAM_STATUS[cam]||'').toUpperCase();
      if(!s) return '<span class="stat off"><span class="dot"></span>—</span>';
      let cls='off', lbl=s.charAt(0)+s.slice(1).toLowerCase().replace(/_/g,' ');
      if(s==='ACTIVE'){ cls='on'; lbl='Active'; }
      else if(s.indexOf('PAUSED')>=0){ cls='off'; lbl='Paused'; }
      else if(s==='ARCHIVED'||s==='DELETED'){ cls='off'; lbl=s.charAt(0)+s.slice(1).toLowerCase(); }
      else if(s.indexOf('ISSUE')>=0||s.indexOf('DISAPPROVED')>=0||s.indexOf('REJECT')>=0){ cls='bad'; lbl='Issues'; }
      return '<span class="stat '+cls+'" title="'+s+'"><span class="dot"></span>'+lbl+'</span>';
    }
    // Bảng Campaign HỢP NHẤT mọi channel: dòng từ ad-platform API (Meta — có Status/CTR/CVR)
    // + dòng chỉ có trong Adjust (vd TikTok — cost do platform đẩy sang, CTR/CVR không có → "—").
    function renderCam(days){
      if(!document.getElementById('camBody')) return;
      const rows=Object.keys(DCAM).map(function(c){
        let sp=0,impr=0,lc=0,inst=0,v3=0;
        days.forEach(function(d){ const a=DCAM[c][d]; if(a){sp+=a[0];impr+=a[1];lc+=a[2];inst+=a[3];v3+=a[4];} });
        return {c:c,ch:'Meta',sp:sp,impr:impr,lc:lc,inst:inst,v3:v3,adj:false};
      }).filter(function(x){return x.impr>0||x.sp>0;});
      Object.keys(DACAM_ADJ).forEach(function(c){
        if(DCAM[c]) return;                       // đã có từ Meta API → không thêm lần 2
        let inst=0,cost=0;
        days.forEach(function(d){ const a=DACAM_ADJ[c][d]; if(a){inst+=a[0];cost+=a[1];} });
        if(inst>0||cost>0.005) rows.push({c:c,ch:CAM_CH[c]||'—',sp:cost*FX,impr:0,lc:0,inst:inst,v3:0,adj:true});
      });
      const vis=rows
        .filter(function(x){ return camFilter==='all' || x.adj || (CAM_STATUS[x.c]||'').toUpperCase()==='ACTIVE'; })
        .sort(function(a,b){return b.sp-a.sp;});
      document.getElementById('camBody').innerHTML = vis.length? vis.map(function(x,i){
        const cost=x.sp/FX,cpi=x.inst?cost/x.inst:0,ctr=x.impr?x.lc/x.impr*100:0,cvr=x.lc?x.inst/x.lc*100:0;
        const cc=cpi<CPI_T[0]?'good':cpi<CPI_T[1]?'warn':'bad',tc=ctr>6?'good':ctr>3?'warn':'bad';
        const obj=CAM_OBJ[x.c]||'—';
        let rev=0; const ac=DACAM_ADJ[x.c];
        if(ac){ days.forEach(function(d){ const a=ac[d]; if(a){ rev+=a[2]; } }); }
        const roas=cost?rev/cost:0;
        const exp=DCAMGEO[x.c]?' expandable':'', car=DCAMGEO[x.c]?'<span class="caret">▸</span> ':'';
        const st=x.adj?'<span class="stat on" title="Đang phát sinh chi phí trong Adjust (channel không có API status)"><span class="dot"></span>Spending</span>':statHtml(x.c);
        const ctrTd=x.adj?'<td class="mut" title="Channel này chưa có ad-platform API — không có CTR">—</td><td class="mut">—</td>'
                         :'<td class="'+tc+'">'+ctr.toFixed(2)+'%</td><td>'+cvr.toFixed(1)+'%</td>';
        return '<tr class="crow'+exp+(i%2?' zeb':'')+'" data-cid="'+x.c+'"><td>'+car+x.c+'</td><td class="angcell"><span class="ang"><b>'+x.ch+'</b></span></td><td class="angcell">'+st+'</td><td class="angcell"><span class="ang"><b>'+obj+'</b></span></td><td>$'+cost.toFixed(2)+'</td><td>'+x.inst.toLocaleString()+'</td><td class="'+cc+'">$'+cpi.toFixed(3)+'</td>'+ctrTd+'<td>$'+rev.toFixed(2)+'</td><td>'+roas.toFixed(2)+'x</td></tr>';
      }).join('')+(function(){
        var T=vis.reduce(function(s,x){
          s.sp+=x.sp;s.impr+=x.impr;s.lc+=x.lc;s.inst+=x.inst;
          var ac=DACAM_ADJ[x.c]; if(ac){ days.forEach(function(d){ var a=ac[d]; if(a){ s.rev+=a[2]; } }); }
          return s;
        },{sp:0,impr:0,lc:0,inst:0,rev:0});
        var cost=T.sp/FX,cpi=T.inst?cost/T.inst:0,ctr=T.impr?T.lc/T.impr*100:0,cvr=T.lc?T.inst/T.lc*100:0,roas=cost?T.rev/cost:0;
        return '<tr class="trow-tot"><td>Total</td><td></td><td></td><td></td><td>$'+cost.toFixed(2)+'</td><td>'+T.inst.toLocaleString()+'</td><td>$'+cpi.toFixed(3)+'</td><td>'+ctr.toFixed(2)+'%</td><td>'+cvr.toFixed(1)+'%</td><td>$'+T.rev.toFixed(2)+'</td><td>'+roas.toFixed(2)+'x</td></tr>';
      })() : '<tr><td colspan="11" style="text-align:center;color:var(--mut)">không có data trong khung thời gian này</td></tr>';
    }
    const QLAB={ABOVE_AVERAGE:'Above avg', AVERAGE:'Average',
      BELOW_AVERAGE_35:'Below avg (35%)', BELOW_AVERAGE_20:'Below avg (20%)', BELOW_AVERAGE_10:'Below avg (10%)'};
    function qLabel(q){ return q&&QLAB[q]?QLAB[q]:'—'; }
    const ANG_RE=new RegExp(__ANGRE__);
    function angOf(cid){
      const m=ANG_RE.exec(cid); if(!m) return '<span class="mut">—</span>';
      const code=m[1], nm=ANGN[code]||'';
      return '<span class="ang"><b>'+code+'</b> '+nm+'</span>';
    }

    // ---------- điều phối ----------
    let curWin='7';
    let camFilter='all';
    function renderAll(){
      const days=daysFor(curWin), prev=prevFor(curWin);
      document.getElementById('rangelbl').textContent = days.length? (days[0]+' → '+days[days.length-1]+' ('+days.length+' ngày)') : '—';
      renderKPIs(days,prev); renderChart(curMetric,days); renderCam(days); renderGeo(days); renderCre(days);
    }
    document.querySelectorAll('.win-btn').forEach(function(b){ b.addEventListener('click',function(){
      document.querySelectorAll('.win-btn').forEach(function(x){x.classList.remove('active');});
      b.classList.add('active'); curWin=b.dataset.w; renderAll();
    });});
    document.querySelectorAll('.cam-btn').forEach(function(b){ b.addEventListener('click',function(){
      document.querySelectorAll('.cam-btn').forEach(function(x){x.classList.remove('active');});
      b.classList.add('active'); camFilter=b.dataset.f; renderCam(daysFor(curWin));
    });});
    document.querySelectorAll('.seg-btn').forEach(function(b){ b.addEventListener('click',function(){
      document.querySelectorAll('.seg-btn').forEach(function(x){x.classList.remove('active');});
      b.classList.add('active'); renderChart(b.dataset.m, daysFor(curWin));
    });});
    let rt; window.addEventListener('resize',function(){ clearTimeout(rt); rt=setTimeout(function(){renderChart(curMetric,daysFor(curWin));},150); });
    // mobile: chạm 1 lát → đổi popup sang lát đó; chạm chỗ khác / scroll → tắt popup
    document.addEventListener('pointerdown',function(e){
      const sl=e.target.closest?e.target.closest('.pieslice'):null;
      if(sl) showGeoTip(sl,e.clientX,e.clientY); else hideGeoTip();
    });
    window.addEventListener('scroll',hideGeoTip,true);

    // click 1 creative → mở/đóng breakdown geo thật (Adjust). Trang Saya không có 2 bảng này → guard null.
    const creB=document.getElementById('creBody');
    if(creB) creB.addEventListener('click',function(e){
      const tr=e.target.closest('tr.crow.expandable'); if(!tr) return;
      const nx=tr.nextElementSibling;
      if(nx&&nx.classList.contains('subrow')){ nx.remove(); tr.classList.remove('open'); return; }
      const sub=document.createElement('tr'); sub.className='subrow';
      sub.innerHTML='<td colspan="9">'+creGeoSub(tr.dataset.cid,daysFor(curWin))+'</td>';
      tr.after(sub); tr.classList.add('open');
    });
    const camB=document.getElementById('camBody');
    if(camB) camB.addEventListener('click',function(e){
      const tr=e.target.closest('tr.crow.expandable'); if(!tr) return;
      const nx=tr.nextElementSibling;
      if(nx&&nx.classList.contains('subrow')){ nx.remove(); tr.classList.remove('open'); return; }
      const sub=document.createElement('tr'); sub.className='subrow';
      sub.innerHTML='<td colspan="11">'+camGeoSub(tr.dataset.cid,daysFor(curWin))+'</td>';
      tr.after(sub); tr.classList.add('open');
    });

    // ---------- thu gọn sidebar (desktop) ----------
    (function(){
      const app=document.querySelector('.app');
      let collapsed=false;
      try { collapsed = localStorage.getItem('navCollapsed')==='1'; } catch(e){}
      app.classList.toggle('nav-collapsed', collapsed);
      document.querySelectorAll('.side-toggle').forEach(function(b){
        b.addEventListener('click',function(){
          collapsed=!app.classList.contains('nav-collapsed');
          app.classList.toggle('nav-collapsed', collapsed);
          try { localStorage.setItem('navCollapsed', collapsed?'1':'0'); } catch(e){}
          window.dispatchEvent(new Event('resize'));  // chart đo lại bề rộng
        });
      });
    })();

    renderAll();
    """.replace("__DAYS__", j_days).replace("__DTOT__", j_dtot).replace("__DGEO__", j_dgeo) \
       .replace("__DCRE__", j_dcre).replace("__DCAM__", j_dcam).replace("__COBJ__", j_cobj) \
       .replace("__CSTAT__", j_cstat).replace("__DACADJ__", j_dacam).replace("__CAMCH__", j_camch) \
       .replace("__DCREGEO__", j_dcregeo) \
       .replace("__DCAMGEO__", j_dcamgeo) \
       .replace("__ANGN__", j_angn).replace("__QR__", j_qr).replace("__FX__", f"{fx:.2f}") \
       .replace("__D1CUT__", json.dumps(d1cut)).replace("__CPIT__", j_cpit) \
       .replace("__ANGRE__", j_angre)

    # ----- phần HTML khác nhau giữa 2 app -----
    ICON_CARDIA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>'
    ICON_SAYA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>'
    CAMPAIGN_PANEL = """
      <div class="panel">
        <div class="panel-head">
          <h2>Campaign</h2>
          <div class="seg" role="tablist" aria-label="Lọc trạng thái campaign">
            <button class="cam-btn active" data-f="all">All</button>
            <button class="cam-btn" data-f="active">Active</button>
          </div>
        </div>
        <div class="scroll"><table>
          <thead><tr><th>Campaign</th><th class="angcol">Channel</th><th class="angcol">Status</th><th class="angcol">Objective</th><th>Spend</th><th>Inst</th><th>CPI</th><th>CTR</th><th title="Install / Click">CVR</th><th>Revenue</th><th>ROAS</th></tr></thead>
          <tbody id="camBody"></tbody>
        </table></div>
      </div>"""
    CREATIVE_PANEL = """
      <div class="panel">
        <h2>Creative (Meta)</h2>
        <div class="scroll"><table>
          <thead><tr><th>Creative</th><th class="angcol">Angle</th><th>Impr</th><th>Inst</th><th>CPI</th><th>CTR</th><th title="Install / Click">CVR</th><th>hook 3s</th><th>Quality</th></tr></thead>
          <tbody id="creBody"></tbody>
        </table></div>
      </div>"""
    if is_saya:
        # Cloudflare Pages: trang Cardia được upload cả index.html LẪN dashboard.html
        # (publish_cloudflare.sh) → link "dashboard.html" chạy đúng cả local lẫn cloud.
        nav_apps = (f'<a class="nav" href="dashboard.html" aria-label="Cardia">{ICON_CARDIA} Cardia</a>'
                    f'<button class="nav active" aria-label="Saya">{ICON_SAYA} Saya</button>')
        side_foot = f'Snapshot <b>{date}</b><br>FX ~{fx:,.0f} VND/$'
        page_desc = f"ROAS / CPI / retention theo geo & creative — Saya (Meta + TikTok, Adjust), snapshot {date}"
        campaign_panel = CAMPAIGN_PANEL
        creative_panel = CREATIVE_PANEL if has_meta else ""
    else:
        nav_apps = (f'<button class="nav active" aria-label="Cardia">{ICON_CARDIA} Cardia</button>'
                    f'<a class="nav" href="saya.html" aria-label="Saya">{ICON_SAYA} Saya</a>')
        side_foot = f'Snapshot <b>{date}</b><br>FX ~{fx:,.0f} VND/$'
        page_desc = f"ROAS / CPI / retention theo geo & creative — Cardia Meta Ads, snapshot {date}"
        campaign_panel = CAMPAIGN_PANEL
        creative_panel = CREATIVE_PANEL

    html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MTD Dashboard · {app_title} — {date}</title>
<meta name="description" content="{page_desc}">
<style>
  :root {{ --bg:#f5f7fb; --card:#ffffff; --card2:#eef2f9; --line:#dde3ef; --txt:#172033;
          --mut:#5f6b82; --good:#0f9d6b; --warn:#c2790f; --bad:#d6454f; --acc:#2f6fe0; --zebra:#f6f8fd; }}
  * {{ box-sizing:border-box; }}
  /* Khoá iOS Safari tự phóng to chữ trong bảng có cột dài (tên campaign) → giữ đúng size như bảng GEO. */
  html {{ -webkit-text-size-adjust:100%; text-size-adjust:100%; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
         font:14px/1.55 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         font-variant-numeric:tabular-nums; }}
  .app {{ display:flex; min-height:100vh; align-items:stretch; }}
  .side {{ width:214px; flex-shrink:0; background:var(--card); border-right:1px solid var(--line);
          padding:20px 14px; display:flex; flex-direction:column; gap:3px; position:sticky; top:0; height:100vh; }}
  .brand {{ display:flex; align-items:center; gap:9px; font-weight:700; font-size:16px; letter-spacing:-.01em; margin:2px 6px 18px; }}
  .brand .logo {{ width:27px; height:27px; border-radius:7px; background:linear-gradient(135deg,var(--acc),#1e478f);
          color:#fff; display:grid; place-items:center; font-size:14px; font-weight:800; }}
  .nav {{ appearance:none; border:0; background:transparent; text-align:left; width:100%; display:flex; align-items:center;
          gap:10px; color:var(--mut); font:inherit; font-size:13.5px; font-weight:600; padding:9px 11px; border-radius:8px;
          cursor:pointer; transition:background .12s,color .12s; }}
  .nav:hover {{ background:var(--card2); color:var(--txt); }}
  .nav.active {{ background:var(--card2); color:var(--acc); }}
  a.nav {{ text-decoration:none; }}
  .nav:focus-visible {{ outline:2px solid var(--acc); outline-offset:1px; }}
  .nav svg {{ width:16px; height:16px; flex-shrink:0; }}
  .nav-sec {{ color:var(--mut); font-size:9.5px; text-transform:uppercase; letter-spacing:.08em; margin:16px 11px 5px; font-weight:600; }}
  .side-foot {{ margin-top:auto; color:var(--mut); font-size:11px; padding:12px 8px 0; border-top:1px solid var(--line); line-height:1.6; }}
  .main {{ flex:1; min-width:0; padding:26px 34px 60px; }}
  .content {{ max-width:none; width:100%; }}
  .page-h {{ font-size:21px; margin:0 0 4px; letter-spacing:-.01em; }}
  .page-sub {{ color:var(--mut); margin:0; font-size:13px; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; margin-bottom:22px; }}
  .head-l {{ display:flex; align-items:center; gap:12px; min-width:0; }}
  .side-toggle {{ flex-shrink:0; appearance:none; width:34px; height:34px; border:1px solid var(--line); background:var(--card);
          border-radius:8px; color:var(--mut); cursor:pointer; display:flex; align-items:center; justify-content:center;
          transition:background .12s,color .12s; }}
  .side-toggle:hover {{ background:var(--card2); color:var(--acc); }}
  .side-toggle:focus-visible {{ outline:2px solid var(--acc); outline-offset:1px; }}
  .side-toggle svg {{ width:17px; height:17px; }}
  h1 {{ font-size:23px; margin:0 0 4px; letter-spacing:-.01em; }}
  .sub {{ color:var(--mut); margin:0; font-size:13px; }}
  .seg {{ display:inline-flex; gap:2px; background:var(--card2); border:1px solid var(--line); border-radius:8px; padding:3px; }}
  .seg-btn,.win-btn,.cam-btn {{ appearance:none; border:0; background:transparent; color:var(--mut); font:inherit; font-size:12.5px; font-weight:600;
             padding:6px 13px; border-radius:6px; cursor:pointer; transition:background .12s,color .12s; }}
  .seg-btn:hover,.win-btn:hover,.cam-btn:hover {{ color:var(--txt); }}
  .seg-btn.active,.win-btn.active,.cam-btn.active {{ background:var(--card); color:var(--acc); box-shadow:0 1px 2px rgba(23,32,51,.12); }}
  .seg-btn:focus-visible,.win-btn:focus-visible,.cam-btn:focus-visible {{ outline:2px solid var(--acc); outline-offset:1px; }}
  .panel-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 14px; }}
  .panel-head h2 {{ margin:0; }}
  .grid {{ display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:8px; margin-bottom:26px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:9px; padding:11px 12px 8px;
         border-top:3px solid var(--line); box-shadow:0 1px 2px rgba(23,32,51,.04); display:flex; flex-direction:column; }}
  .kpi-l {{ color:var(--mut); font-size:9.5px; text-transform:uppercase; letter-spacing:.04em; }}
  .kpi-v {{ font-size:19px; font-weight:680; letter-spacing:-.02em; white-space:nowrap; margin-top:3px; }}
  .kpi-delta {{ font-size:10.5px; margin-top:4px; font-weight:600; white-space:nowrap; }}
  .kpi-delta .vs {{ color:var(--mut); font-weight:500; }}
  .kpi-delta.up {{ color:var(--good); }} .kpi-delta.down {{ color:var(--bad); }} .kpi-delta.flat {{ color:var(--mut); }}
  .kpi.good {{ border-top-color:var(--good); }} .kpi.bad {{ border-top-color:var(--bad); }} .kpi.warn {{ border-top-color:var(--warn); }}
  .spark {{ width:100%; height:34px; display:block; margin-top:8px; }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px; margin-bottom:20px; box-shadow:0 1px 3px rgba(23,32,51,.04); }}
  .panel h2 {{ font-size:12px; margin:0 0 14px; color:var(--mut); text-transform:uppercase; letter-spacing:.07em; font-weight:600; }}
  .chart-box {{ background:var(--card2); border:1px solid var(--line); border-radius:8px; padding:14px 12px 8px; }}
  .chartwrap {{ position:relative; width:100%; }}
  .chartwrap svg {{ display:block; width:100%; height:auto; }}
  .gridline {{ stroke:var(--line); stroke-dasharray:3 5; stroke-width:1; opacity:.7; }}
  .axislbl {{ fill:var(--mut); font-size:10.5px; }}
  .axisttl {{ fill:var(--mut); font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; opacity:.85; }}
  .cross {{ stroke:var(--mut); stroke-width:1; }}
  .hband {{ fill:var(--txt); opacity:.07; }}
  .hcross {{ stroke:var(--mut); stroke-dasharray:4 4; stroke-width:1; opacity:.55; }}
  .vpill rect, .xpill rect {{ fill:#2f3e46; }}
  .vpill text, .xpill text {{ fill:#fff; font-size:11px; font-weight:700; }}
  .tip {{ position:absolute; pointer-events:none; background:var(--card); border:1px solid var(--line); border-radius:8px;
         padding:7px 10px; box-shadow:0 4px 14px rgba(23,32,51,.14); white-space:nowrap; transform:translate(-50%,-118%); z-index:2; }}
  .tip .d {{ color:var(--mut); font-size:11px; margin-bottom:4px; }}
  .tip .vrow {{ font-size:12px; display:flex; align-items:center; gap:6px; line-height:1.55; }}
  .tip .vrow b {{ font-weight:700; margin-left:auto; padding-left:8px; }}
  .tip .dotc {{ width:8px; height:8px; border-radius:2px; display:inline-block; flex-shrink:0; }}
  .barrow {{ display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }}
  .rangelbl {{ color:var(--mut); font-size:12px; margin-left:auto; }}
  .legend {{ display:inline-flex; gap:13px; align-items:center; font-size:11.5px; color:var(--mut); }}
  .legend i {{ display:inline-flex; align-items:center; gap:5px; font-style:normal; }}
  .legend .sw {{ width:11px; height:11px; border-radius:2px; display:inline-block; }}
  .legend .swl {{ width:15px; height:0; border-top:2.4px solid; display:inline-block; }}
  .scroll {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; min-width:560px; }}
  th,td {{ text-align:right; padding:8px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }}
  th:first-child,td:first-child {{ text-align:left; }}
  th {{ color:var(--mut); font-weight:600; font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; }}
  tr:last-child td {{ border-bottom:none; }}
  tbody tr.zeb {{ background:var(--zebra); }}
  .subt tbody tr:nth-child(even) {{ background:var(--zebra); }}
  tbody tr.trow-tot {{ background:var(--card2); border-top:2px solid var(--line); }}
  tbody tr.trow-tot td {{ font-weight:700; color:var(--txt); }}
  tbody tr.trow-tot:hover {{ background:var(--card2); }}
  tbody tr.geo-other td {{ color:var(--mut); font-style:italic; }}
  /* ---- GEO split: donut + bảng ---- */
  .geo-split {{ display:flex; gap:18px; align-items:stretch; }}
  .geo-left {{ flex:0 0 540px; display:flex; flex-direction:column; justify-content:center; align-items:center; padding:6px 0; }}
  .geo-right {{ flex:1; min-width:0; }}
  .pie-graphic {{ width:100%; display:flex; justify-content:center; }}
  .donut {{ width:100%; max-width:540px; height:auto; }}
  .pieslice {{ stroke:var(--card); stroke-width:2; transition:opacity .14s; cursor:pointer; }}
  .donut:hover .pieslice {{ opacity:.3; }}
  .donut .pieslice:hover {{ opacity:1; }}
  .donut-num {{ fill:var(--txt); font-size:46px; font-weight:700; font-variant-numeric:tabular-nums; }}
  .donut-lbl {{ fill:var(--mut); font-size:14px; letter-spacing:.1em; text-transform:uppercase; }}
  .pie-in-name {{ font-size:14px; font-weight:700; pointer-events:none; }}
  .pie-in-pct {{ font-size:12px; font-weight:600; font-variant-numeric:tabular-nums; opacity:.92; pointer-events:none; }}
  .pie-empty {{ color:var(--mut); font-size:13px; padding:48px 0; text-align:center; }}
  .geo-tip {{ position:fixed; z-index:50; min-width:150px; background:var(--card); border:1px solid var(--line);
              border-radius:10px; padding:10px 12px; box-shadow:0 8px 24px rgba(23,32,51,.16); pointer-events:none; }}
  .geo-tip .gt-h {{ display:flex; align-items:center; gap:7px; font-weight:700; color:var(--txt); font-size:13px; margin-bottom:7px; }}
  .geo-tip .gt-dot {{ width:10px; height:10px; border-radius:3px; flex:0 0 auto; }}
  .geo-tip .gt-row {{ display:flex; justify-content:space-between; gap:18px; font-size:12.5px; color:var(--mut); padding:2px 0; }}
  .geo-tip .gt-row b {{ color:var(--txt); font-variant-numeric:tabular-nums; }}
  @media (max-width:880px) {{ .geo-split {{ flex-direction:column; }} .geo-left {{ flex:0 0 auto; }} .donut {{ max-width:420px; }} }}
  .good {{ color:var(--good); }} .warn {{ color:var(--warn); }} .bad {{ color:var(--bad); }}
  .mono {{ font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--acc); }}
  .mut {{ color:var(--mut); }}
  td.angcell, th.angcol {{ text-align:left; }}
  .angwrap {{ display:inline-flex; gap:4px; flex-wrap:wrap; }}
  .ang {{ display:inline-block; background:var(--card2); border:1px solid var(--line); color:var(--txt);
         border-radius:5px; padding:1px 7px; font-size:11px; white-space:nowrap; }}
  .ang b {{ color:var(--acc); font-weight:700; }}
  .ang-x {{ color:var(--mut); }}
  .stat {{ display:inline-flex; align-items:center; gap:6px; font-size:11.5px; white-space:nowrap; color:var(--mut); }}
  .stat .dot {{ width:7px; height:7px; border-radius:50%; background:var(--mut); flex-shrink:0; }}
  .stat.on {{ color:var(--good); }} .stat.on .dot {{ background:var(--good); }}
  .stat.bad {{ color:var(--bad); }} .stat.bad .dot {{ background:var(--bad); }}
  .crow.expandable {{ cursor:pointer; }}
  .crow.expandable:hover {{ background:var(--card2); }}
  .caret {{ display:inline-block; color:var(--mut); font-size:9px; transition:transform .12s; }}
  .crow.open .caret {{ transform:rotate(90deg); }}
  .subrow > td {{ padding:0; background:var(--card2); border-bottom:1px solid var(--line); }}
  .subwrap {{ padding:10px 14px 12px; }}
  .subttl {{ color:var(--mut); font-size:11px; margin-bottom:7px; }}
  .subt {{ width:auto; min-width:0; background:var(--card); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
  .subt th, .subt td {{ padding:6px 14px; font-size:12px; border-bottom:1px solid var(--line); }}
  .subt th {{ font-size:9.5px; }}
  .subt tr:last-child td {{ border-bottom:none; }}
  .subempty {{ padding:12px 14px; color:var(--mut); font-size:12px; }}
  .adjf {{ font-size:8.5px; color:var(--mut); margin-left:3px; vertical-align:super; cursor:help; }}
  .subt tbody tr.cty-x {{ display:none; }}
  .subwrap.allc .subt tbody tr.cty-x {{ display:table-row; }}
  .morebtn {{ margin-top:8px; padding:5px 12px; font-size:11px; font-weight:600; color:var(--txt);
    background:var(--card); border:1px solid var(--line); border-radius:7px; cursor:pointer; }}
  .morebtn:hover {{ border-color:var(--mut); }}
  .note {{ color:var(--mut); font-size:12px; margin-top:10px; line-height:1.5; }}
  @media (min-width:861px) {{ .app.nav-collapsed .side {{ display:none; }} }}
  @media (max-width:860px) {{
    .side-toggle {{ display:none; }}
    .app {{ flex-direction:column; }}
    .side {{ width:auto; height:auto; position:sticky; top:0; z-index:5; flex-direction:row; align-items:center; gap:4px;
            border-right:0; border-bottom:1px solid var(--line); padding:10px 14px; overflow-x:auto; }}
    .brand {{ margin:0 12px 0 0; }}
    .nav {{ width:auto; white-space:nowrap; }}
    .nav-sec, .side-foot {{ display:none; }}
    .main {{ padding:18px 16px 50px; }}
    .grid {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
    .head {{ margin-bottom:18px; }}
    .head .seg {{ overflow-x:auto; max-width:100%; }}
  }}
  @media (max-width:520px) {{
    .main {{ padding:14px 12px 40px; }}
    h1 {{ font-size:19px; }}
    .sub, .page-sub {{ font-size:12px; }}
    .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; margin-bottom:18px; }}
    .kpi-v {{ font-size:17px; }}
    .panel {{ padding:13px 11px; }}
    .barrow {{ gap:7px; }}
    .win-btn, .seg-btn {{ padding:6px 9px; }}
    .legend {{ width:100%; order:3; }}
  }}
</style>
<div class="app">
  <aside class="side">
    <div class="brand"><span class="logo">M</span> MTD Dashboard</div>
    <div class="nav-sec">Apps</div>
    {nav_apps}
    <div class="side-foot">{side_foot}
    </div>
  </aside>

  <main class="main">
    <section id="view-overview" class="content">
      <div class="head">
        <div class="head-l">
          <button class="side-toggle" aria-label="Ẩn/hiện menu" title="Ẩn/hiện menu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
          </button>
          <div>
            <h1 class="page-h">{app_title} Dashboard</h1>
            <p class="page-sub">Last updated {built}</p>
          </div>
        </div>
        <div class="seg" role="tablist" aria-label="Khung thời gian">
          <button class="win-btn" data-w="today">Today</button>
          <button class="win-btn" data-w="yesterday">Yesterday</button>
          <button class="win-btn active" data-w="7">7D</button>
          <button class="win-btn" data-w="14">14D</button>
          <button class="win-btn" data-w="30">30D</button>
          <button class="win-btn" data-w="all">All</button>
        </div>
      </div>

      <div class="grid" id="grid"></div>

      <div class="panel">
        <div class="barrow">
          <div class="seg" role="tablist" aria-label="Chọn metric">
            <button class="seg-btn active" data-m="install">Install</button>
            <button class="seg-btn" data-m="roas">ROAS</button>
          </div>
          <span class="legend" id="chartlegend"></span>
          <span class="rangelbl" id="rangelbl"></span>
        </div>
        <div class="chart-box">
          <div class="chartwrap" id="chartwrap"><div id="svghost"></div><div class="tip" id="tip" hidden></div></div>
        </div>
      </div>

      {campaign_panel}

      <div class="panel">
        <h2>GEO (Adjust)</h2>
        <div class="geo-tip" id="geoTip" hidden></div>
        <div class="geo-split">
          <div class="geo-left"><div id="geoPie"></div></div>
          <div class="geo-right">
            <div class="scroll"><table>
              <thead><tr><th>Geo</th><th>Inst</th><th>Cost</th><th>Rev</th><th>CPI</th><th>LTV</th><th>ROAS</th><th>D1</th><th>ROAS D7</th></tr></thead>
              <tbody id="geoBody"></tbody>
            </table></div>
          </div>
        </div>
      </div>

      {creative_panel}
    </section>
  </main>
</div>
<script>{APP}</script>"""

    out = HERE / ("saya.html" if is_saya else "dashboard.html")
    out.write_text(html, encoding="utf-8")
    T = totals_py(DTOT, all_days)
    extra = f" · {len(DCRE)} creative · FX={fx:,.0f}" if has_meta else ""
    print(f"✅ {app_title} → {out}")
    print(f"   {len(all_days)} ngày · installs={T[0]} cost=${T[1]:.2f} rev=${T[2]:.2f}{extra}")


def main():
    d = latest_export()
    if not d:
        sys.exit("❌ Chưa có export nào trong exports/")
    build(d, "cardia")
    if (d / "adjust_saya.csv").exists():
        build(d, "saya")
    else:
        print("⏭ Không có adjust_saya.csv trong export này — bỏ qua trang Saya "
              "(điền ADJUST_SAYA_QUERY vào .env rồi pull lại).")
    print("→ Publish: bash publish_cloudflare.sh (deploy dashboard.html + saya.html).")


def totals_py(DTOT, days):
    inst = sum(DTOT[d][0] for d in days)
    cost = sum(DTOT[d][1] for d in days)
    rev = sum(DTOT[d][2] for d in days)
    return inst, cost, rev


if __name__ == "__main__":
    main()
