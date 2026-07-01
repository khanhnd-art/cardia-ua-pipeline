#!/bin/bash
# Cardia — đẩy dashboard.html lên Cloudflare Pages (host tĩnh, URL cố định) qua wrangler.
# Auth bằng token trong .env. Bỏ qua êm nếu chưa cấu hình → KHÔNG làm hỏng pipeline.
#
# Dùng:  bash publish_cloudflare.sh              (deploy dashboard.html)
#        bash publish_cloudflare.sh --create      (tạo project Pages 1 lần)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE" || exit 1

# launchd chạy PATH tối giản → thêm chỗ node/wrangler
export PATH="/opt/homebrew/bin:$PATH"

envget() { grep -E "^$1=" .env 2>/dev/null | head -1 | sed -E "s/^$1=//; s/^[\"']//; s/[\"']$//; s/[[:space:]]*$//"; }
export CLOUDFLARE_API_TOKEN="$(envget CLOUDFLARE_API_TOKEN)"
export CLOUDFLARE_ACCOUNT_ID="$(envget CLOUDFLARE_ACCOUNT_ID)"
# Tên project Pages (= subdomain .pages.dev). Đổi ở .env để tái dùng cho app khác.
PROJECT="$(envget CF_PAGES_PROJECT)"; PROJECT="${PROJECT:-ua-dashboard}"

if [ -z "$CLOUDFLARE_API_TOKEN" ] || [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
  echo "⚠️  Bỏ qua publish Cloudflare — chưa có CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID trong .env"
  exit 0
fi
if ! command -v wrangler >/dev/null 2>&1; then
  echo "⚠️  Bỏ qua publish — chưa cài wrangler (npm i -g wrangler)"
  exit 0
fi

# --- tạo project (chạy 1 lần) ---
if [ "${1:-}" = "--create" ]; then
  wrangler pages project create "$PROJECT" --production-branch main
  exit $?
fi

if [ ! -f dashboard.html ]; then
  echo "⚠️  Bỏ qua publish — chưa có dashboard.html"
  exit 0
fi

# Cloudflare Pages deploy theo THƯ MỤC; index.html = trang gốc
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp dashboard.html "$TMP/index.html"

if wrangler pages deploy "$TMP" --project-name "$PROJECT" --branch main --commit-dirty=true 2>&1; then
  echo "✅ Đã publish Cloudflare Pages (project=$PROJECT)"
else
  echo "❌ Publish Cloudflare lỗi (không ảnh hưởng pull chính)"
fi
exit 0
