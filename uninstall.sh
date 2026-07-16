#!/bin/bash
# Keycloak Auth Manager 卸载脚本

set -e

SERVICE_NAME="keycloak-auth-manager"
INSTALL_DIR="/opt/keycloak-auth-manager"
BACKUP_DIR="/tmp/keycloak_auth_manager_backup"

echo "=== 卸载 Keycloak Auth Manager ==="

# 停止服务
echo "停止服务..."
systemctl stop $SERVICE_NAME || true
systemctl disable $SERVICE_NAME || true

# 删除服务文件
echo "删除 systemd 服务..."
rm -f /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload

# 删除安装目录（保留配置与密钥）
echo "删除安装目录..."
read -p "是否保留全套配置文件 (config.json, data.json, encryption.key)? (y/n): " keep_config
if [ "$keep_config" = "y" ]; then
    rm -rf $BACKUP_DIR
    mkdir -p $BACKUP_DIR
    [ -f "$INSTALL_DIR/data.json" ] && cp $INSTALL_DIR/data.json $BACKUP_DIR/
    [ -f "$INSTALL_DIR/config.json" ] && cp $INSTALL_DIR/config.json $BACKUP_DIR/
    [ -f "$INSTALL_DIR/encryption.key" ] && cp $INSTALL_DIR/encryption.key $BACKUP_DIR/
fi
rm -rf $INSTALL_DIR

echo ""
echo "=== 卸载完成 ==="
if [ "$keep_config" = "y" ]; then
    echo "全套配置文件与加密密钥已备份到: $BACKUP_DIR"
    echo "（下次重新安装时，脚本将自动还原密钥，以确保旧数据能够被正常解密）"
fi
