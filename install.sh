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

# 检查基础系统依赖 (Docker, Python3, pip3)
echo "[1] 检查基础系统依赖 (Docker, Python3, pip3)..."

MISSING_APT=""
MISSING_YUM=""
MISSING_CMD=""

if ! command -v docker &> /dev/null; then
    MISSING_APT="$MISSING_APT docker.io"
    MISSING_YUM="$MISSING_YUM docker"
    MISSING_CMD="$MISSING_CMD docker"
fi
if ! command -v docker-compose &> /dev/null; then
    MISSING_APT="$MISSING_APT docker-compose-v2"
    MISSING_YUM="$MISSING_YUM docker-compose-plugin"
    MISSING_CMD="$MISSING_CMD docker-compose"
fi
if ! command -v python3 &> /dev/null; then
    MISSING_APT="$MISSING_APT python3"
    MISSING_YUM="$MISSING_YUM python3"
    MISSING_CMD="$MISSING_CMD python3"
fi
if ! command -v pip3 &> /dev/null; then
    MISSING_APT="$MISSING_APT python3-pip"
    MISSING_YUM="$MISSING_YUM python3-pip"
    MISSING_CMD="$MISSING_CMD pip3"
fi

if [ -n "$MISSING_CMD" ]; then
    echo "    ✗ 发现缺失基础命令:$MISSING_CMD"
    read -p "    是否尝试自动一次性安装缺失的基础环境? (y/n) [y]: " install_deps_now
    install_deps_now=${install_deps_now:-y}
    if [ "$install_deps_now" = "y" ]; then
        echo "    正在自动安装缺失的依赖..."
        if command -v apt-get &>/dev/null; then
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -y -q
            apt-get install -y -q $MISSING_APT
        elif command -v yum &>/dev/null; then
            yum install -y -q $MISSING_YUM
        else
            echo "    ✗ 未知的包管理器，请手动安装$MISSING_CMD"
            check_passed=false
        fi
        
        # 兼容 docker-compose 命令（V2）
        if [ -f /usr/libexec/docker/cli-plugins/docker-compose ] && ! command -v docker-compose &> /dev/null; then
            ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
            ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/bin/docker-compose
        fi
        
        # 验证是否全部安装成功
        if ! command -v docker &> /dev/null || ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
            echo "    ✗ 部分基础依赖自动安装失败，请检查系统网络或手动安装。"
            check_passed=false
        else
            echo "    ✓ 缺失的基础依赖安装完成"
        fi
    else
        check_passed=false
    fi
else
    echo "    ✓ 基础系统依赖 (Docker, Python3, pip3) 已全部存在"
fi

# 检查 Docker 是否运行
if command -v docker &> /dev/null; then
    if docker ps &> /dev/null; then
        echo "    ✓ Docker 服务运行中"
    else
        echo "    ✗ Docker 服务未运行"
        read -p "    是否尝试启动 Docker 服务? (y/n) [y]: " start_docker_now
        start_docker_now=${start_docker_now:-y}
        if [ "$start_docker_now" = "y" ]; then
            echo "    正在启动 Docker 服务..."
            if systemctl start docker; then
                echo "    ✓ Docker 服务已启动"
                systemctl enable docker &>/dev/null || true
            else
                echo "    ✗ Docker 服务启动失败"
                echo "    请手动启动: systemctl start docker"
                check_passed=false
            fi
        else
            check_passed=false
        fi
    fi
fi

# 检查 1Panel/OpenResty
echo "[2] 检查 1Panel/OpenResty..."
PANEL_DIR="/opt/1panel"
OPENRESTY_DIR="/opt/1panel/apps/openresty/openresty"

if [ -d "$PANEL_DIR" ]; then
    echo "    ✓ 1Panel 已安装: $PANEL_DIR"
else
    echo "    ✗ 1Panel 未安装"
    read -p "    是否尝试自动安装 1Panel? (y/n) [y]: " install_panel_now
    install_panel_now=${install_panel_now:-y}
    if [ "$install_panel_now" = "y" ]; then
        echo "    正在下载并运行 1Panel 安装脚本..."
        if bash -c "$(curl -sSL https://resource.fit2cloud.com/1panel/package/v2/quick_start.sh)"; then
            echo "    ✓ 1Panel 安装完成"
        else
            echo "    ✗ 1Panel 安装失败"
            echo "    请手动运行安装命令: bash -c \"\$(curl -sSL https://resource.fit2cloud.com/1panel/package/v2/quick_start.sh)\""
            check_passed=false
        fi
    else
        check_passed=false
    fi
fi

if [ -d "$OPENRESTY_DIR" ]; then
    echo "    ✓ OpenResty 已安装: $OPENRESTY_DIR"
else
    echo "    ! OpenResty 未安装（建议在 1Panel 应用商店中搜索并安装 OpenResty）"
fi

# 检查网站目录
SITES_DIR="$OPENRESTY_DIR/www/sites"
if [ -d "$SITES_DIR" ]; then
    echo "    ✓ 网站目录存在: $SITES_DIR"
else
    echo "    ! 网站目录不存在: $SITES_DIR (将随着在 1Panel 中创建网站时自动创建)"
fi

# 检查 Keycloak 容器
echo "[3] 检查 Keycloak..."
if command -v docker &> /dev/null && docker ps &> /dev/null; then
    KEYCLOAK_RUNNING=$(docker ps --filter "name=keycloak" --format "{{.Names}}" | head -1)
    if [ -n "$KEYCLOAK_RUNNING" ]; then
        echo "    ✓ Keycloak 容器运行中: $KEYCLOAK_RUNNING"
    else
        KEYCLOAK_EXISTS=$(docker ps -a --filter "name=keycloak" --format "{{.Names}}" | head -1)
        if [ -n "$KEYCLOAK_EXISTS" ]; then
            echo "    ! Keycloak 容器存在但未运行: $KEYCLOAK_EXISTS"
            read -p "    是否尝试启动该容器? (y/n) [y]: " start_kc_now
            start_kc_now=${start_kc_now:-y}
            if [ "$start_kc_now" = "y" ]; then
                if docker start "$KEYCLOAK_EXISTS" &> /dev/null; then
                    echo "    ✓ 容器 $KEYCLOAK_EXISTS 已启动"
                    KEYCLOAK_RUNNING="$KEYCLOAK_EXISTS"
                else
                    echo "    ✗ 容器启动失败"
                    check_passed=false
                fi
            else
                check_passed=false
            fi
        else
            echo "    ✗ Keycloak 容器不存在"
            read -p "    是否现在自动部署 Keycloak 容器? (y/n) [y]: " deploy_kc_now
            deploy_kc_now=${deploy_kc_now:-y}
            if [ "$deploy_kc_now" = "y" ]; then
                echo ""
                echo "--- 部署 Keycloak 容器配置 ---"
                read -p "    选择数据库类型 (h2/postgres) [h2]: " kc_db_type
                kc_db_type=${kc_db_type:-h2}
                
                read -p "    设置 Keycloak 管理员用户名 [admin]: " kc_admin_user
                kc_admin_user=${kc_admin_user:-admin}
                
                read -sp "    设置 Keycloak 管理员密码 [admin123]: " kc_admin_pass
                echo ""
                kc_admin_pass=${kc_admin_pass:-admin123}
                
                read -p "    设置 Keycloak 映射端口 [8080]: " kc_port
                kc_port=${kc_port:-8080}
                
                kc_db_pass=""
                if [ "$kc_db_type" = "postgres" ]; then
                    read -sp "    设置 PostgreSQL 数据库密码 [KcDbPassWord_2026]: " kc_db_pass
                    echo ""
                    kc_db_pass=${kc_db_pass:-KcDbPassWord_2026}
                fi
                
                echo "    正在调用 deploy_keycloak.sh 部署容器..."
                if bash deploy_keycloak.sh "$kc_db_type" "$kc_admin_user" "$kc_admin_pass" "$kc_port" "$kc_db_pass"; then
                    echo "    ✓ Keycloak 容器部署成功"
                    KEYCLOAK_RUNNING="keycloak"
                else
                    echo "    ✗ Keycloak 容器部署失败"
                    check_passed=false
                fi
            else
                check_passed=false
            fi
        fi
    fi
else
    echo "    ✗ 无法检查 Keycloak (Docker 未运行)"
    check_passed=false
fi

# 检查 oauth2-proxy 镜像
echo "[4] 检查 oauth2-proxy..."
if command -v docker &> /dev/null && docker ps &> /dev/null; then
    if docker images | grep -q "oauth2-proxy"; then
        echo "    ✓ oauth2-proxy 镜像已下载"
    else
        echo "    ! oauth2-proxy 镜像未下载（首次使用时会自动拉取）"
    fi
else
    echo "    ✗ 无法检查 oauth2-proxy 镜像 (Docker 未运行)"
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

# 获取本地 IP 供默认值使用
local_ip=$(hostname -I | awk '{print $1}')
local_ip=${local_ip:-127.0.0.1}

# 自动探测运行中 Keycloak 容器的映射端口
kc_detected_port=""
if [ -n "$KEYCLOAK_RUNNING" ]; then
    kc_detected_port=$(docker port "$KEYCLOAK_RUNNING" 8080 2>/dev/null | head -n1 | cut -d':' -f2)
fi
kc_detected_port=${kc_detected_port:-${kc_port:-8080}}

default_kc_url="http://$local_ip:$kc_detected_port"

# Keycloak URL
read -p "Keycloak 服务地址 [$default_kc_url]: " KEYCLOAK_URL
KEYCLOAK_URL=${KEYCLOAK_URL:-$default_kc_url}

# 验证 Keycloak URL 是否可访问
echo "    测试 Keycloak 连接..."
if curl -s -o /dev/null -w "%{http_code}" "$KEYCLOAK_URL" --max-time 10 | grep -q "200\|302\|303\|307\|404"; then
    echo "    ✓ Keycloak URL 可访问"
else
    echo "    ! Keycloak URL 无法访问，请确认地址正确（若容器刚启动请稍候）"
fi

# Keycloak Admin 用户名
default_kc_admin=${kc_admin_user:-admin}
read -p "Keycloak Admin 用户名 [$default_kc_admin]: " KEYCLOAK_ADMIN
KEYCLOAK_ADMIN=${KEYCLOAK_ADMIN:-$default_kc_admin}

# Keycloak Admin 密码
default_kc_pass=${kc_admin_pass:-}
if [ -n "$default_kc_pass" ]; then
    read -sp "Keycloak Admin 密码 [使用自动部署时设置的密码]: " KEYCLOAK_PASSWORD
    echo ""
    KEYCLOAK_PASSWORD=${KEYCLOAK_PASSWORD:-$default_kc_pass}
else
    read -sp "Keycloak Admin 密码 [YOUR_PASSWORD]: " KEYCLOAK_PASSWORD
    echo ""
    KEYCLOAK_PASSWORD=${KEYCLOAK_PASSWORD:-}
fi

# Web 控制台端口
read -p "Web 控制台端口 [8088]: " WEB_PORT
WEB_PORT=${WEB_PORT:-8088}

# 检查端口是否被占用 (优先使用 ss, 次之 netstat)
port_in_use="no"
if command -v ss &> /dev/null; then
    if ss -tuln | grep -q ":$WEB_PORT "; then
        port_in_use="yes"
    fi
elif command -v netstat &> /dev/null; then
    if netstat -tuln | grep -q ":$WEB_PORT"; then
        port_in_use="yes"
    fi
fi

if [ "$port_in_use" = "yes" ]; then
    echo "    ! 端口 $WEB_PORT 已被占用"
    read -p "    是否使用其他端口? 输入新端口: " NEW_PORT
    WEB_PORT=${NEW_PORT:-$WEB_PORT}
fi

# Keycloak 容器名称
default_kc_container=${KEYCLOAK_RUNNING:-keycloak}
read -p "Keycloak 容器名称 [$default_kc_container]: " KEYCLOAK_CONTAINER
KEYCLOAK_CONTAINER=${KEYCLOAK_CONTAINER:-$default_kc_container}

# 1Panel API 端口
read -p "1Panel API 端口 [40455]: " ONEPANEL_PORT
ONEPANEL_PORT=${ONEPANEL_PORT:-40455}

# 1Panel API Key
read -p "1Panel API Key (如果不使用 API 自动建站可留空): " ONEPANEL_API_KEY
ONEPANEL_API_KEY=${ONEPANEL_API_KEY:-}

# Apple 主题安装选择
echo ""
echo "=== Apple 主题安装 ==="
read -p "是否安装 Apple 登录主题? (y/n) [n]: " INSTALL_THEME
INSTALL_THEME=${INSTALL_THEME:-n}

# 检测容器运行状态
if ! docker ps --filter "name=^/${KEYCLOAK_CONTAINER}$" --format "{{.Names}}" | grep -q "^${KEYCLOAK_CONTAINER}$"; then
    echo "    ! 警示: 容器 $KEYCLOAK_CONTAINER 未运行，如果已在其他地方运行或非 Docker 部署可忽略此警告。"
fi

echo ""
echo "=== 配置确认 ==="
echo ""
echo "  Keycloak URL:    $KEYCLOAK_URL"
echo "  Keycloak Admin:  $KEYCLOAK_ADMIN"
echo "  Keycloak 容器:   $KEYCLOAK_CONTAINER"
echo "  Web 端口:        $WEB_PORT"
echo "  1Panel 端口:     $ONEPANEL_PORT"
echo "  1Panel API Key:  $(if [ -n "$ONEPANEL_API_KEY" ]; then echo '已配置(隐藏)'; else echo '未配置'; fi)"
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
echo "[2] 复制项目文件..."
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
    echo "[3] 创建配置文件..."
    cat > $INSTALL_DIR/config.json << CONFIG
{
    "keycloak_url": "$KEYCLOAK_URL",
    "keycloak_admin": "$KEYCLOAK_ADMIN",
    "keycloak_password": "$KEYCLOAK_PASSWORD",
    "keycloak_container": "$KEYCLOAK_CONTAINER",
    "web_port": $WEB_PORT,
    "onepanel_port": $ONEPANEL_PORT,
    "onepanel_api_key": "$ONEPANEL_API_KEY",
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
echo "[4] 创建 systemd 服务..."
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

# [7] 安装 Apple 主题
if [ "$INSTALL_THEME" = "y" ]; then
    echo "[7] 安装 Apple 主题..."
    THEME_DIR="/opt/keycloak/themes/apple"
    echo "    创建本地备份目录 $THEME_DIR..."
    mkdir -p "$THEME_DIR"
    if [ -d "themes/apple/login" ]; then
        cp -r themes/apple/login "$THEME_DIR"/
        echo "    ✓ Apple 主题本地文件已保存"
        
        # 复制到 Keycloak 容器内部
        if docker ps --filter "name=^/${KEYCLOAK_CONTAINER}$" --format "{{.Names}}" | grep -q "^${KEYCLOAK_CONTAINER}$"; then
            echo "    正在复制主题到容器 $KEYCLOAK_CONTAINER..."
            # 确保容器内的 themes 目录存在并复制
            docker exec "$KEYCLOAK_CONTAINER" mkdir -p /opt/keycloak/themes 2>/dev/null || true
            docker cp themes/apple "$KEYCLOAK_CONTAINER":/opt/keycloak/themes/
            echo "    重启 Keycloak 容器以加载新主题..."
            docker restart "$KEYCLOAK_CONTAINER" >/dev/null
            echo "    ✓ Apple 主题已成功安装到容器 $KEYCLOAK_CONTAINER 且已重启该容器"
        else
            echo "    ! 未检测到运行中的 Keycloak 容器 $KEYCLOAK_CONTAINER，无法自动复制主题到容器内。"
            echo "    请在 Keycloak 容器启动后手动执行此命令复制主题："
            echo "    docker cp themes/apple $KEYCLOAK_CONTAINER:/opt/keycloak/themes/"
        fi
        echo "    说明: 导入后，请在 Keycloak Admin Console 的 Realm Settings -> Themes 中选择 Login Theme 为 'apple'。"
    else
        echo "    ! 本地主题文件 themes/apple/login 不存在，跳过安装。"
    fi
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
