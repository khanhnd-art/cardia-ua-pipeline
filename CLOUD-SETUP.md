# Đưa pipeline lên cloud — GitHub Actions

Chạy `pull_data.py → dashboard.py → publish_cloudflare.sh` mỗi giờ trên GitHub, không cần
máy Mac mở. Deploy vẫn ra đúng URL `.pages.dev` như cũ.

## 0. Meta token — ĐÃ OK, không cần làm gì
Token trong `.env` đã là **System User token** (`cardia-reporting`), **không hết hạn**, scope
`ads_read`. Đã kiểm bằng `debug_token`: `type=SYSTEM_USER · expires_at=0 (never)`. → Bỏ qua bước này.
> Kiểm lại bất kỳ lúc nào:
> ```bash
> TOK=$(grep -E '^META_ACCESS_TOKEN=' .env | head -1 | cut -d= -f2-)
> curl -s "https://graph.facebook.com/v21.0/debug_token?input_token=$TOK&access_token=$TOK"
> ```

## 1. Tạo repo GitHub (public)
```bash
cd 03-tracking-attribution/auto-pull
git init -b main
git add .                       # .gitignore đã loại .env, exports/, logs/, dashboard.html
git commit -m "Cardia UA pipeline → GitHub Actions"
gh repo create cardia-ua-pipeline --public --source=. --push
```
> Public an toàn vì credential nằm ở **GitHub Secrets**, KHÔNG trong code. `.gitignore` đảm bảo
> `.env` và data không bao giờ bị commit. (Kiểm tra: `git status` không được thấy `.env`.)

## 2. Đẩy credential lên GitHub Secrets
Đọc `.env` local và đẩy tự động (cần `brew install gh` + `gh auth login`):
```bash
bash push-secrets.sh <owner>/cardia-ua-pipeline
```
Hoặc thủ công: repo → **Settings → Secrets and variables → Actions → New secret**, thêm 9 key:
`META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `ADJUST_API_TOKEN`, `ADJUST_REPORT_QUERY`,
`ADJUST_CREATIVE_QUERY`, `SINCE`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_PAGES_PROJECT`.

## 3. Chạy thử
Repo → tab **Actions → Cardia UA pipeline → Run workflow** (nút bên phải). Xem log từng bước,
bước "Publish" phải in `✅ Đã publish Cloudflare Pages`. Mở lại URL `.pages.dev` để xác nhận.

## 4. Tắt pipeline local (tránh chạy 2 nơi)
Sau khi cloud chạy ổn, gỡ launchd trên Mac để không deploy chồng:
```bash
launchctl unload ~/Library/LaunchAgents/com.cardia.autopull.plist
```
> Muốn bật lại: `launchctl load ~/Library/LaunchAgents/com.cardia.autopull.plist`

## Lưu ý vận hành
- **Cron GitHub theo giờ UTC**, hay bị trễ/bỏ mốc lúc tải cao (thực tế 01–03/07 bị drop rất nặng ở `*/30`).
  Đã né bằng 2 lớp: (1) cron đặt **phút 7** (tránh peak :00/:30); (2) **watchdog trên Mac**
  (`watchdog_dispatch.sh` + launchd `com.cardia.watchdog`, phút 37 mỗi giờ): run cuối quá 75 phút
  → tự `gh workflow run` (dispatch không bao giờ bị drop). Máy tắt thì chỉ còn lớp (1).
- **Rule 60 ngày (GitHub tự tắt scheduled workflow nếu repo không có commit): đã tự giải** —
  mỗi ngày workflow commit 1 snapshot exports vào nhánh `data` (run 22–23h VN) nên repo luôn active.
- **Lịch sử data:** nhánh `data` → `snapshots/<YYYY-MM-DD>/` = bộ CSV "số nhìn thấy hôm đó".
- Sửa tần suất: đổi dòng `cron:` trong `.github/workflows/pipeline.yml`.
- Đổi token/secret sau này: chạy lại `push-secrets.sh` hoặc sửa trực tiếp trong Settings → Secrets.
