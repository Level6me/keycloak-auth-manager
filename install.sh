#!/bin/bash
# Keycloak Auth Manager 一键部署脚本（含依赖检查）
# 用法: bash install.sh

set -e

INSTALL_DIR="/opt/keycloak-auth-manager"
SERVICE_NAME="keycloak-auth-manager"

echo ""
echo "=========================================="
echo "  Keycloak Auth Manager 一键部署"
echo "=========================================="
echo ""

# ==================== 依赖检查 ====================
echo "=== 检查依赖 ==="
echo ""

check_passed=true

# 检查 Docker
echo "[1] 检查 Docker..."
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo "    ✓ Docker 已安装: $docker_version"
else
    echo "    ✗ Docker 未安装"
    echo "    安装命令: curl -fsSL https://get.docker.com | sh"
    check_passed=false
fi

# 检查 Docker 是否运行
if docker ps &> /dev/null; then
    echo "    ✓ Docker 服务运行中"
else
    echo "    ✗ Docker 服务未运行"
    echo "    启动命令: systemctl start docker"
    check_passed=false
fi

# 检查 Python3
echo "[2] 检查 Python3..."
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version)
    echo "    ✓ Python3 已安装: $python_version"
else
    echo "    ✗ Python3 未安装"
    echo "    安装命令: yum install python3 或 apt install python3"
    check_passed=false
fi

# 检查 pip3
if command -v pip3 &> /dev/null; then
    echo "    ✓ pip3 已安装"
else
    echo "    ✗ pip3 未安装"
    echo "    安装命令: yum install python3-pip 或 apt install python3-pip"
    check_passed=false
fi

# 检查 1Panel/OpenResty
echo "[3] 检查 1Panel/OpenResty..."
PANEL_DIR="/opt/1panel"
OPENRESTY_DIR="/opt/1panel/apps/openresty/openresty"

if [ -d "$PANEL_DIR" ]; then
    echo "    ✓ 1Panel 已安装: $PANEL_DIR"
else
    echo "    ✗ 1Panel 未安装"
    echo "    安装命令: curl -sSL https://resource.fit2cloud.com/1panel/package快速安装v1.10.sh | bash"
    check_passed=false
fi

if [ -d "$OPENRESTY_DIR" ]; then
    echo "    ✓ OpenResty 已安装: $OPENRESTY_DIR"
else
    echo "    ✗ OpenResty 未安装（需在 1Panel 中安装）"
    check_passed=false
fi

# 检查网站目录
SITES_DIR="$OPENRESTY_DIR/www/sites"
if [ -d "$SITES_DIR" ]; then
    echo "    ✓ 网站目录存在: $SITES_DIR"
else
    echo "    ✗ 网站目录不存在: $SITES_DIR"
    check_passed=false
fi

# 检查 Keycloak 容器
echo "[4] 检查 Keycloak..."
KEYCLOAK_RUNNING=$(docker ps --filter "name=keycloak" --format "{{.Names}}" | head -1)
if [ -n "$KEYCLOAK_RUNNING" ]; then
    echo "    ✓ Keycloak 容器运行中: $KEYCLOAK_RUNNING"
else
    KEYCLOAK_EXISTS=$(docker ps -a --filter "name=keycloak" --format "{{.Names}}" | head -1)
    if [ -n "$KEYCLOAK_EXISTS" ]; then
        echo "    ! Keycloak 容器存在但未运行: $KEYCLOAK_EXISTS"
        echo "    启动命令: docker start $KEYCLOAK_EXISTS"
    else
        echo "    ✗ Keycloak 容器不存在"
        echo "    需要先安装 Keycloak"
        check_passed=false
    fi
fi

# 检查 oauth2-proxy 镜像
echo "[5] 检查 oauth2-proxy..."
if docker images | grep -q "oauth2-proxy"; then
    echo "    ✓ oauth2-proxy 镜像已下载"
else
    echo "    ! oauth2-proxy 镜像未下载（首次使用时会自动拉取）"
fi

echo ""

if [ "$check_passed" = false ]; then
    echo "=========================================="
    echo "  依赖检查失败！"
    echo "=========================================="
    echo ""
    echo "请先安装缺失的依赖，然后重新运行此脚本。"
    echo ""
    read -p "是否继续部署（忽略检查失败）? (y/n): " force_continue
    if [ "$force_continue" != "y" ]; then
        exit 1
    fi
    echo ""
fi

# ==================== 交互式配置 ====================
echo "=== 配置信息 ==="
echo ""
echo "请输入配置信息（直接回车使用默认值）:"
echo ""

# Keycloak URL
read -p "Keycloak 服务地址 [https://keycloak.your-domain.com]: " KEYCLOAK_URL
KEYCLOAK_URL=${KEYCLOAK_URL:-}

# 验证 Keycloak URL 是否可访问
echo "    测试 Keycloak 连接..."
if curl -s -o /dev/null -w "%{http_code}" "$KEYCLOAK_URL" --max-time 10 | grep -q "200\|302"; then
    echo "    ✓ Keycloak URL 可访问"
else
    echo "    ! Keycloak URL 无法访问，请确认地址正确"
fi

# Keycloak Admin 用户名
read -p "Keycloak Admin 用户名 [admin]: " KEYCLOAK_ADMIN
KEYCLOAK_ADMIN=${KEYCLOAK_ADMIN:-admin}

# Keycloak Admin 密码
read -sp "Keycloak Admin 密码 [YOUR_PASSWORD]: " KEYCLOAK_PASSWORD
echo ""
KEYCLOAK_PASSWORD=${KEYCLOAK_PASSWORD:-}

# Web 控制台端口
read -p "Web 控制台端口 [8088]: " WEB_PORT
WEB_PORT=${WEB_PORT:-8088}

# 检查端口是否被占用
if netstat -tuln | grep -q ":$WEB_PORT"; then
    echo "    ! 端口 $WEB_PORT 已被占用"
    read -p "    是否使用其他端口? 输入新端口: " NEW_PORT
    WEB_PORT=${NEW_PORT:-$WEB_PORT}
fi

# Keycloak 容器名称
read -p "Keycloak 容器名称 [$KEYCLOAK_RUNNING]: " KEYCLOAK_CONTAINER
KEYCLOAK_CONTAINER=${KEYCLOAK_CONTAINER:-$KEYCLOAK_RUNNING}

# Apple 主题安装
echo ""
echo "=== Apple 主题安装 ==="
read -p "是否安装 Apple 登录主题? (y/n): " INSTALL_THEME
if [ "$INSTALL_THEME" = "y" ]; then
    THEME_DIR="/opt/keycloak/themes/apple"
    echo "    安装 Apple 主题到 $THEME_DIR..."
    mkdir -p $THEME_DIR
    if [ -d "themes/apple/login" ]; then
        cp -r themes/apple/login $THEME_DIR/
        echo "    ✓ Apple 主题已安装"
        echo "    在 Keycloak Admin Console 选择 Login Theme: apple"
    else
        echo "    ! 主题文件不存在，请手动安装"
    fi
fi
if ! docker ps --filter "name=$KEYCLOAK_CONTAINER" --format "{{.Names}}" | grep -q "$KEYCLOAK_CONTAINER"; then
    echo "    ! 容器 $KEYCLOAK_CONTAINER 未运行"
fi

echo ""
echo "=== 配置确认 ==="
echo ""
echo "  Keycloak URL:    $KEYCLOAK_URL"
echo "  Keycloak Admin:  $KEYCLOAK_ADMIN"
echo "  Keycloak 容器:   $KEYCLOAK_CONTAINER"
echo "  Web 端口:        $WEB_PORT"
echo "  安装目录:        $INSTALL_DIR"
echo ""

read -p "确认部署? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "取消部署"
    exit 0
fi

# ==================== 开始部署 ====================
echo ""
echo "=== 开始部署 ==="

# 检查项目文件
if [ ! -f "app.py" ]; then
    echo "错误: 请在项目目录运行此脚本"
    exit 1
fi

# 安装依赖
echo "[1] 安装 Python 依赖 (flask, cryptography, requests)..."
pip3 install flask cryptography requests --break-system-packages --ignore-installed -q 2>/dev/null || pip install flask cryptography requests --break-system-packages --ignore-installed -q
echo "    ✓ 依赖包已安装"

# 创建安装目录
echo "[2] 创建安装目录..."
mkdir -p $INSTALL_DIR
echo "    ✓ 目录已创建: $INSTALL_DIR"

# 复制文件
echo "[3] 复制项目文件..."
cp app.py $INSTALL_DIR/
cp -r static $INSTALL_DIR/
cp -r templates $INSTALL_DIR/
cp -r nginx-auth $INSTALL_DIR/ 2>/dev/null || true
echo "    ✓ 文件已复制"

# 尝试还原备份的配置（支持卸载保留恢复）
if [ -f "/tmp/keycloak_auth_manager_backup/encryption.key" ]; then
    echo "    检测到备份的加密密钥，正在还原..."
    cp /tmp/keycloak_auth_manager_backup/encryption.key $INSTALL_DIR/
fi
if [ -f "/tmp/keycloak_auth_manager_backup/config.json" ]; then
    echo "    检测到备份的配置文件，正在还原..."
    cp /tmp/keycloak_auth_manager_backup/config.json $INSTALL_DIR/
fi
if [ -f "/tmp/keycloak_auth_manager_backup/data.json" ]; then
    echo "    检测到备份的数据文件，正在还原..."
    cp /tmp/keycloak_auth_manager_backup/data.json $INSTALL_DIR/
fi

# 如果没有还原配置文件，则创建新的配置文件
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    echo "[4] 创建配置文件..."
    cat > $INSTALL_DIR/config.json << CONFIG
{
    "keycloak_url": "$KEYCLOAK_URL",
    "keycloak_admin": "$KEYCLOAK_ADMIN",
    "keycloak_password": "$KEYCLOAK_PASSWORD",
    "keycloak_container": "$KEYCLOAK_CONTAINER",
    "web_port": $WEB_PORT,
    "install_dir": "$INSTALL_DIR"
}
CONFIG
    echo "    ✓ 配置已生成"
fi

if [ ! -f "$INSTALL_DIR/data.json" ]; then
    # 创建空数据文件
    echo '{}' > $INSTALL_DIR/data.json
fi

# 创建 systemd 服务
echo "[5] 创建 systemd 服务..."
cat > /etc/systemd/system/$SERVICE_NAME.service << SERVICE
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

# 启动服务
echo "[6] 启动服务..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME
sleep 3

# 检查状态
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "    ✓ 服务已启动"
else
    echo "    ! 服务启动失败，请检查日志"
fi

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "访问地址: http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
echo ""
echo "文件位置:"
echo "  程序:   $INSTALL_DIR/app.py"
echo "  配置:   $INSTALL_DIR/config.json"
echo "  数据:   $INSTALL_DIR/data.json"
echo "  日志:   通过 journalctl 集中管理"
echo ""
echo "管理命令:"
echo "  systemctl status $SERVICE_NAME    # 查看状态"
echo "  systemctl restart $SERVICE_NAME   # 重启"
echo "  systemctl stop $SERVICE_NAME      # 停止"
echo "  journalctl -u $SERVICE_NAME -f    # 日志"
echo ""
