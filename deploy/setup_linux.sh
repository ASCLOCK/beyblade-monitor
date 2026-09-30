#!/usr/bin/env bash
# Beyblade 監測 - Linux 伺服器一鍵安裝（systemd 常駐，每 30 分鐘掃描）
# 用法：sudo bash setup_linux.sh
set -e

APP_DIR="/opt/beyblade-monitor"
SERVICE="beyblade-monitor.service"

echo "==> 檢查 Python3 ..."
command -v python3 >/dev/null 2>&1 || { echo "找不到 python3，請先安裝：apt install python3 (Debian/Ubuntu) 或 yum install python3 (CentOS)"; exit 1; }
python3 --version

echo "==> 確認程式位置：$APP_DIR"
[ -f "$APP_DIR/monitor.py" ] || { echo "找不到 $APP_DIR/monitor.py，請先把專案資料夾放到 $APP_DIR"; exit 1; }

echo "==> 安裝 systemd 服務 ..."
cp "$APP_DIR/deploy/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

echo "==> 完成！"
echo "    查看狀態：  systemctl status $SERVICE"
echo "    查看日誌：  journalctl -u $SERVICE -f"
echo "    停止服務：  systemctl stop $SERVICE"
echo "    測試通知：  cd $APP_DIR && python3 monitor.py --test"
