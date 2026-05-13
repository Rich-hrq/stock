#!/bin/bash
set -e

echo "=== 1. 复制配置文件 ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/nginx-stock.conf" /etc/nginx/sites-available/stock

echo "=== 2. 替换默认站点 ==="
rm -f /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/stock /etc/nginx/sites-enabled/stock

echo "=== 3. 测试配置 ==="
nginx -t

echo "=== 4. 重载 nginx ==="
systemctl reload nginx

echo ""
echo "=== 配置完成 ==="
nginx -v
systemctl status nginx --no-pager -l
