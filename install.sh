#!/bin/bash
# Keycloak Auth Manager 一键部署脚本
# 用法: bash install.sh

set -e

INSTALL_DIR="/opt/keycloak-auth-manager"
SERVICE_NAME="keycloak-auth-manager"

echo "=== Keycloak Auth Manager 一键部署 ==="

# 检查是否在项目目录
if [ ! -f "app.py" ]; then
    echo "错误: 请在项目目录运行此脚本"
    exit 1
fi

# 安装依赖
echo "安装 Python 依赖..."
pip3 install flask -q || pip install flask -q

# 创建安装目录
echo "创建安装目录: $INSTALL_DIR"
mkdir -p $INSTALL_DIR

# 复制文件
echo "复制项目文件..."
cp app.py $INSTALL_DIR/
cp Dockerfile $INSTALL_DIR/
cp -r static $INSTALL_DIR/
cp -r templates $INSTALL_DIR/
cp -r nginx-auth $INSTALL_DIR/
cp data.json.example $INSTALL_DIR/data.json.example

# 创建空配置文件（如果不存在）
if [ ! -f "$INSTALL_DIR/data.json" ]; then
    echo '{}' > $INSTALL_DIR/data.json
fi

# 创建 systemd 服务
echo "创建 systemd 服务..."
cat > /etc/systemd/system/$SERVICE_NAME.service << 'SERVICE'
[Unit]
Description=Keycloak Auth Manager Web Console
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/keycloak-auth-manager
ExecStart=/usr/bin/python3 /opt/keycloak-auth-manager/app.py
Restart=always
RestartSec=5
StandardOutput=append:/opt/keycloak-auth-manager/app.log
StandardError=append:/opt/keycloak-auth-manager/app.log

[Install]
WantedBy=multi-user.target
SERVICE

# 启动服务
echo "启动服务..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# 等待服务启动
sleep 3

# 检查状态
echo ""
echo "=== 服务状态 ==="
systemctl status $SERVICE_NAME --no-pager

echo ""
echo "=== 部署完成 ==="
echo "访问地址: http://服务器IP:8088"
echo "日志文件: $INSTALL_DIR/app.log"
echo "配置文件: $INSTALL_DIR/data.json"
echo ""
echo "管理命令:"
echo "  systemctl status $SERVICE_NAME   # 查看状态"
echo "  systemctl restart $SERVICE_NAME  # 重启服务"
echo "  systemctl stop $SERVICE_NAME     # 停止服务"
