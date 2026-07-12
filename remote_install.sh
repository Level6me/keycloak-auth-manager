#!/bin/bash
# 远程非交互部署脚本
# 自动读取配置并完成部署

set -e

INSTALL_DIR="/opt/keycloak-auth-manager"
SERVICE_NAME="keycloak-auth-manager"

echo "=========================================="
echo "  开始远程非交互式部署"
echo "=========================================="

# 1. 安装 Python 依赖
echo "[1] 安装 Python3 依赖包..."
sudo pip3 install flask cryptography requests --break-system-packages --ignore-installed -q || sudo pip install flask cryptography requests --break-system-packages --ignore-installed -q
echo "    ✓ 依赖包已安装"

# 2. 创建安装目录并同步文件
echo "[2] 创建安装目录并复制项目文件..."
sudo mkdir -p $INSTALL_DIR
sudo cp -r /home/ubuntu/keycloak-auth-manager/app.py $INSTALL_DIR/
sudo cp -r /home/ubuntu/keycloak-auth-manager/static $INSTALL_DIR/
sudo cp -r /home/ubuntu/keycloak-auth-manager/templates $INSTALL_DIR/
echo "    ✓ 文件复制完成"

# 3. 创建配置文件
echo "[3] 创建 config.json 配置文件..."
sudo tee $INSTALL_DIR/config.json > /dev/null << CONFIG
{
  "keycloak_url": "http://127.0.0.1:8080",
  "keycloak_admin": "admin",
  "keycloak_password": "KeycloakAdmin_2026_Secure!",
  "keycloak_container": "keycloak",
  "web_port": 8088,
  "install_dir": "$INSTALL_DIR",
  "onepanel_api_key": "P01Wovo36NVwRqyNrHqYrqfs7fJis0vl",
  "onepanel_port": 18080
}
CONFIG
sudo chmod 600 $INSTALL_DIR/config.json
echo "    ✓ 配置文件创建成功"

# 4. 创建空数据文件
if [ ! -f "$INSTALL_DIR/data.json" ]; then
    echo "[4] 创建 data.json 数据文件..."
    echo '{}' | sudo tee $INSTALL_DIR/data.json > /dev/null
    sudo chmod 600 $INSTALL_DIR/data.json
    echo "    ✓ 数据文件已创建"
fi

# 5. 复制 Apple 登录主题到 Keycloak 容器中
echo "[5] 配置 Apple 登录主题..."
if sudo docker ps --filter "name=keycloak" --format "{{.Names}}" | grep -q "keycloak"; then
    sudo docker exec keycloak mkdir -p /opt/keycloak/themes
    if [ -d "/home/ubuntu/keycloak-auth-manager/themes/apple/login" ]; then
        sudo docker cp /home/ubuntu/keycloak-auth-manager/themes/apple/login keycloak:/opt/keycloak/themes/
        echo "    ✓ Apple 主题已复制到 Keycloak 容器内 (/opt/keycloak/themes/)"
    else
        echo "    ! 未找到本地 Apple 主题目录，跳过"
    fi
else
    echo "    ! Keycloak 容器未运行，跳过 Apple 主题拷贝"
fi

# 6. 创建 systemd 服务
echo "[6] 创建 systemd 服务文件..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << SERVICE
[Unit]
Description=Keycloak Auth Manager Web Console
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE
echo "    ✓ 服务文件已创建"

# 7. 启动服务
echo "[7] 重载并启动 systemd 服务..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

sleep 3
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    echo ""
    echo "=========================================="
    echo "  部署成功！"
    echo "=========================================="
    echo "Web 控制台访问地址: http://43.155.173.146:8088"
    echo ""
else
    echo "✗ 服务启动失败，详情日志："
    sudo journalctl -u $SERVICE_NAME -n 50 --no-pager
    exit 1
fi
