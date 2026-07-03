# Auto-pull Meta + Adjust — hướng dẫn setup

Kéo data Meta Ads (delivery: spend/CPI/CTR/hook-rate/quality) + Adjust (revenue/ROAS/retention theo cohort) tự động ra CSV để phân tích. Setup **1 lần**, sau đó chỉ chạy `python3 pull_data.py`.

> Vì sao 2 nguồn: CTR/hook-rate/Quality Ranking **chỉ Meta có**; cohort ROAS/retention/ad_revenue **chỉ Adjust có** (revenue gốc từ AdMob → đẩy vào Adjust → Adjust gán attribution + cohort). Meta KHÔNG thấy revenue.

---

## PHẦN A — Meta: lấy token + Ad Account ID

**A1. Tạo (hoặc dùng) 1 Meta App**
1. Vào https://developers.facebook.com → **My Apps** → **Create App**.
2. Use case chọn **Other** → loại **Business** → đặt tên (vd `Cardia Reporting`) → Create.
3. Trong app → **Add Product** → thêm **Marketing API**.

**A2. Tạo System User token (trong Business Manager)**
1. Vào https://business.facebook.com → **Business Settings** (Cài đặt doanh nghiệp).
2. **Users → System Users** → **Add** → tên `cardia-reporting`, role **Admin** → Create.
3. Chọn system user vừa tạo → **Add Assets**:
   - **Apps** → chọn app ở bước A1 → bật **Full control / Manage**.
   - **Ad Accounts** → chọn tài khoản quảng cáo Cardia → bật **View performance** (trở lên).
4. Bấm **Generate New Token** → chọn app A1 → **Token expiration: Never** → tick quyền **`ads_read`** và **`read_insights`** → **Generate**.
5. **COPY token ngay** (chỉ hiện 1 lần) → dán vào `META_ACCESS_TOKEN`.

**A3. Lấy Ad Account ID**
- Business Settings → **Accounts → Ad Accounts** → copy dãy số → thêm tiền tố `act_`.
  Ví dụ ID `1234567890` → `META_AD_ACCOUNT_ID=act_1234567890`.
  (Hoặc lấy từ URL Ads Manager: `...act=1234567890...`)

---

## PHẦN B — Adjust: lấy API token + report query

**B1. API token**
1. Mở Adjust (Datascape) → bấm avatar/tên (góc) → **Account Settings**.
2. Tìm mục **API Token** (token Reporting API cấp theo user — anh là admin nên thấy hết data).
3. Copy → dán vào `ADJUST_API_TOKEN`.

**B2a. Lấy App Token (định danh app Cardia)**
- Adjust → mở app **Cardia** → **All Settings** (hoặc bánh răng ⚙️ → App settings).
- Tìm dòng **App Token** — chuỗi ~12 ký tự (vd `abc123def456`). Đây KHÁC API token.

**B2b. Ghép `ADJUST_REPORT_QUERY` — bắt đầu TỐI GIẢN cho chạy được**
> Mẹo: dùng 3 metric chắc chắn tồn tại trước (`installs, cost, ad_revenue`) để pipeline xanh đã, rồi thêm ROAS/retention sau. Tên metric cohort hay đổi theo account → đừng nhồi hết ngay.

Dán dòng này vào `.env` (thay `APPTOKEN` bằng App Token ở B2a):
```
ADJUST_REPORT_QUERY=/reports-service/report?app_token__in=APPTOKEN&dimensions=day,campaign,country&metrics=installs,cost,ad_revenue
```

**B2c. (sau khi chạy OK) thêm ROAS/retention**
Nối thêm vào sau `metrics=...`, ví dụ: `,roas,retention_rate_d1,retention_rate_d7`.
Nếu Adjust báo lỗi tên metric → mở **Datascape → tạo report → bấm "..." / Share → "Copy API call"** để lấy **đúng tên slug** account anh đang dùng, rồi thay vào phần `metrics=`. (Không cần ghi `date_period`/`format` — script tự thêm.)

**B2e. (tùy chọn) Thêm dimension / creative-level — soi retention theo từng creative**
Query chính hiện đã gồm `sessions,daus,waus` để `analyze.py` tự in **SESSION CHECK** (xác định retention thật hay tracking đứt).
Để soi **retention/ROAS theo từng creative** (việc mục C cần), thêm biến `ADJUST_CREATIVE_QUERY` vào `.env`:
1. Datascape → tạo report, kéo thêm dimension **`adgroup`** (= ad set Meta) và/hoặc **`creative`** vào hàng → **Copy API call**.
2. Dán phần URL sau `automate.adjust.com` vào `ADJUST_CREATIVE_QUERY` (mẫu có sẵn trong `.env`).
3. Chạy lại — sinh thêm `adjust_creative.csv`, `analyze.py` in bảng **ADJUST theo CREATIVE/ADGROUP**.
> An toàn: query creative-level có try/except riêng — token dimension sai chỉ skip phần này, **KHÔNG làm hỏng pull chính**. Lưu ý retention creative-level cần Meta đẩy đủ data adgroup/creative sang Adjust qua partner integration.

**B2d. Test nhanh bằng curl TRƯỚC khi chạy script** (thay 2 token):
```bash
curl -s -H "Authorization: Bearer YOUR_API_TOKEN" \
"https://automate.adjust.com/reports-service/report?app_token__in=YOUR_APP_TOKEN&date_period=2026-06-13:2026-06-28&dimensions=day,campaign&metrics=installs,cost,ad_revenue"
```
- Ra **JSON có số** → đúng → bỏ phần query vào `.env`.
- `401` = sai API token · lỗi báo tên metric = sửa lại `metrics=` (xem B2c).

---

## PHẦN C — Điền .env & chạy

1. Copy file mẫu: `cp .env.example .env`
2. Mở `.env`, điền 4 giá trị: `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `ADJUST_API_TOKEN`, `ADJUST_REPORT_QUERY`.
3. Chạy:
   ```bash
   cd 03-tracking-attribution/auto-pull
   python3 pull_data.py
   ```
4. Data ra ở `exports/<ngày-hôm-nay>/`: `meta_campaign.csv`, `meta_ad.csv`, `adjust_report.csv`.
5. Báo Claude: *"đã pull data ngày <hôm nay>"* → tôi đọc thẳng các CSV đó & viết phân tích vào testing matrix.

---

## PHẦN D — Script phụ trợ (sau khi đã pull)

| Lệnh | Tác dụng | Output |
|---|---|---|
| `python3 analyze.py` | In bảng tổng hợp geo / campaign / creative + SESSION CHECK (+ creative-level nếu có) | stdout |
| `python3 dashboard.py` | Sinh dashboard HTML self-contained (KPI · xu hướng ngày · geo · creative) | `dashboard.html` → publish Cloudflare Pages |
| `bash watchdog_dispatch.sh` | Check GitHub có bỏ mốc cron không, quá 75p thì tự kích run (launchd gọi phút 37) | `logs/watchdog.log` |

Quy trình mỗi kỳ: `python3 pull_data.py && python3 analyze.py` (xem nhanh) hoặc thêm `&& python3 dashboard.py` để có cả dashboard. Bình thường KHÔNG cần chạy tay — GitHub Actions tự chạy hourly (xem `CLOUD-SETUP.md`).

**Lịch sử data:** mỗi ngày 1 snapshot CSV được commit vào nhánh **`data`** của repo (folder `snapshots/<ngày>/`, chụp ở run 22–23h VN) — muốn xem "số nhìn thấy hôm X" thì mở nhánh đó trên GitHub.

---

## ⚠️ Bảo mật & lưu ý
- **KHÔNG commit `.env`** (chứa token). Chỉ commit `.env.example`.
- Token Meta System-User là quyền truy cập tài khoản QC — giữ kín như mật khẩu.
- Nếu chỉ chạy Meta hoặc chỉ Adjust: để trống nhóm còn lại, script tự bỏ qua.
- Lỗi `HTTP 190` (Meta) = token sai/hết hạn · `HTTP 401` (Adjust) = sai API token.
- Lỗi `#200 ads_read permission` = token thiếu scope → app cần use case **"Measure ad performance data with Marketing API"** (Add use cases → Ads and monetization), rồi Generate token tick `ads_read`.
- Lỗi `#100 ... not valid for fields` = Meta đổi tên field (đã xử lý: 3s-view lấy từ `actions/video_view`).
