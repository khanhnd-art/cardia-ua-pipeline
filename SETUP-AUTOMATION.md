# Tự động hoá pipeline (auto-run định kỳ)

Mục tiêu: máy tự `pull → analyze → dashboard → weekly report` định kỳ, KHỎI chạy tay.

## 2 lớp tự động (khác nhau)

| Lớp | Làm gì | Khi nào chạy | Bền? |
|---|---|---|---|
| **A. launchd (khuyến nghị)** | Chạy `run_pipeline.sh`: pull data + sinh dashboard + báo cáo tuần | Theo lịch, kể cả khi KHÔNG mở Claude | ✅ Sống độc lập |
| **B. Claude phân tích** | Đọc data mới, viết nhận định vào báo cáo/testing matrix | Chỉ khi mở session Claude | ❌ Cần anh mở Claude |

→ Lớp A lo phần **kéo + tổng hợp số** (việc máy làm được một mình). Lớp B (diễn giải) làm khi anh mở Claude và nói *"phân tích kỳ mới nhất"* — tôi đọc `_latest_analysis.txt` / CSV mới rồi viết.

---

## Cài lớp A — launchd (macOS)

**Lịch mặc định:** **5 mốc/ngày giờ VN — 10:00 / 13:00 / 16:00 / 19:00 / 22:00** (xem số nhiều lần trong ngày). Reporting TZ của Adjust+Meta là GMT‑7 (ngày đóng sổ lúc 14:00 VN), pull re-fetch toàn range mỗi lần nên số ngày trước **tự sửa khi settle**. Data có trễ ~15'–vài giờ → chạy >4 lần/ngày ít giá trị thêm.

Đổi số mốc: sửa mảng `<dict>` trong `StartCalendarInterval` (plist). Muốn 1 lần/ngày: để 1 dict. Muốn đều mỗi N giây bất kể giờ: thay bằng `<key>StartInterval</key><integer>10800</integer>` (3h).

```bash
# 1. Copy plist vào LaunchAgents của user
cp "/Users/khanhnguyen/Desktop/Cardia/03-tracking-attribution/auto-pull/com.cardia.autopull.plist" \
   ~/Library/LaunchAgents/

# 2. Nạp job
launchctl load -w ~/Library/LaunchAgents/com.cardia.autopull.plist

# 3. Kiểm tra đã nạp
launchctl list | grep cardia

# (chạy thử ngay không cần chờ tới giờ)
launchctl start com.cardia.autopull
```

**Đổi lịch:** sửa `Hour`/`Minute` trong plist. Muốn "vài ngày/lần" thay vì hằng ngày → thay block `StartCalendarInterval` bằng:
```xml
<key>StartInterval</key><integer>172800</integer>   <!-- 48h = 2 ngày -->
```
Sửa xong: `launchctl unload` rồi `load -w` lại.

**Gỡ:**
```bash
launchctl unload -w ~/Library/LaunchAgents/com.cardia.autopull.plist
rm ~/Library/LaunchAgents/com.cardia.autopull.plist
```

**Log:** mỗi lần chạy ghi vào `auto-pull/logs/<ngày>.log`; lỗi launchd ở `logs/launchd.err.log`. Bản phân tích mới nhất luôn ở `auto-pull/_latest_analysis.txt`.

> ⚠️ macOS có thể hỏi quyền cho `cron`/script lần đầu. launchd ổn định hơn cron cũ. Nếu máy ngủ đúng giờ hẹn, job chạy bù khi thức.

---

## Cài lớp A — crontab (thay thế, nếu thích cron hơn)
```bash
crontab -e
# thêm dòng (hằng ngày 09:50 VN):
50 9 * * * /Users/khanhnguyen/Desktop/Cardia/03-tracking-attribution/auto-pull/run_pipeline.sh
# hoặc 2 ngày/lần:
50 9 */2 * * /Users/khanhnguyen/Desktop/Cardia/03-tracking-attribution/auto-pull/run_pipeline.sh
```

---

## Nút "Pull data mới" trên dashboard (trigger thủ công)

Muốn bấm 1 nút để pull ngay (thay vì chờ tới mốc giờ), mở dashboard **qua server local**:
```bash
cd /Users/khanhnguyen/Desktop/Cardia/03-tracking-attribution/auto-pull
python3 serve.py        # → http://localhost:8787/
```
Nút **"Pull data mới"** ở góc dưới sidebar sẽ gọi `run_pipeline.sh` (pull → dashboard → weekly report) rồi tự reload trang khi xong. Trạng thái hiện ngay dưới nút.

> ⚠️ Nút chỉ chạy khi mở qua `serve.py` (http://localhost). Mở bằng `file://` hoặc bản publish claude.ai → nút báo "cần mở qua server local" (vì trình duyệt không cho web tĩnh chạy lệnh máy). Đổi port: `CARDIA_PORT=9000 python3 serve.py`.

## Lớp B — nhờ Claude phân tích định kỳ
Mở Claude trong workspace này và nói: **"phân tích kỳ mới nhất"** → tôi đọc data mới + viết nhận định vào [báo cáo tuần](../../05-analytics-reporting/weekly/) và [testing matrix](../../02-creative/04_creative-testing-matrix.md). Báo cáo tuần **không bị ghi đè** (đã chống), nên narrative tôi viết được giữ nguyên qua các lần auto-run.
