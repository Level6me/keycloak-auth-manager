#!/bin/bash
# Keycloak Auth Manager 卸载脚本

set -e

SERVICE_NAME="keycloak-auth-manager"
INSTALL_DIR="/opt/keycloak-auth-manager"

echo "=== 卸载 Keycloak Auth Manager ==="

# 停止服务
echo "停止服务..."
systemctl stop $SERVICE_NAME || true
systemctl disable $SERVICE_NAME || true

# 删除服务文件
echo "删除 systemd 服务..."
rm -f /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload

# 删除安装目录（保留配置）
echo "删除安装目录..."
read -p "是否保留配置文件 data.json? (y/n): " keep_config
if [ "$keep_config" = "y" ]; then
    mv $INSTALL_DIR/data.json /tmp/data.json.bak
fi
rm -rf $INSTALL_DIR

echo ""
echo "=== 卸载完成 ==="
if [ "$keep_config" = "y" ]; then
    echo "配置已备份到: /tmp/data.json.bak"
fi
