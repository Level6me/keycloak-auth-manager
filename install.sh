#!/usr/bin/env bash
# ==============================================================================
# Keycloak Auth Manager 一键部署脚本（全自动检测、依赖修复与双模式兼容）
# 支持方式:
#   1. curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/install.sh | bash
#   2. git clone ... && cd keycloak-auth-manager && sudo bash install.sh
# ==============================================================================

set -e

INSTALL_DIR="/opt/keycloak-auth-manager"
SERVICE_NAME="keycloak-auth-manager"
REPO_URL="https://github.com/Level6me/keycloak-auth-manager.git"

# 终端安全输入辅助函数（防止 curl | bash 管道破坏吞食脚本内容）
prompt_input() {
    local prompt_text="$1"
    local var_name="$2"
    local default_val="$3"
    local is_secret="${4:-false}"
    local user_val=""

    if [ -t 0 ]; then
        if [ "$is_secret" = "true" ]; then
            read -sp "$prompt_text" user_val || true
            echo ""
        else
            read -p "$prompt_text" user_val || true
        fi
    elif [ -e /dev/tty ]; then
        if [ "$is_secret" = "true" ]; then
            read -sp "$prompt_text" user_val < /dev/tty || true
            echo ""
        else
            read -p "$prompt_text" user_val < /dev/tty || true
        fi
    else
        user_val=""
    fi
    eval "$var_name=\"${user_val:-$default_val}\""
}

echo ""
echo "=========================================="
echo "  Keycloak Auth Manager 一键部署"
echo "=========================================="
echo ""

# 0. 准备项目源文件 (若通过 curl | bash 远程执行，则自动拉取最新仓库源码)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
SOURCE_DIR=""
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/app.py" ] && [ -f "$SCRIPT_DIR/deploy_keycloak.sh" ]; then
    SOURCE_DIR="$SCRIPT_DIR"
elif [ -f "./app.py" ] && [ -f "./deploy_keycloak.sh" ]; then
    SOURCE_DIR="$(pwd)"
fi

if [ -z "$SOURCE_DIR" ]; then
    echo "[0] 检测到远程管道执行模式，正在自动获取最新项目源码..."
    TMP_SRC="/tmp/keycloak-auth-manager-src-$(date +%s)"
    rm -rf "$TMP_SRC"
    if command -v git >/dev/null 2>&1; then
        git clone "$REPO_URL" "$TMP_SRC" -q
    else
        echo "    正在安装 git 以获取源码..."
        if command -v apt-get >/dev/null 2>&1; then
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -y -q && apt-get install -y -q git
        elif command -v yum >/dev/null 2>&1; then
            yum install -y -q git
        fi
        git clone "$REPO_URL" "$TMP_SRC" -q
    fi
    SOURCE_DIR="$TMP_SRC"
    echo "    ✓ 源码已就绪: $SOURCE_DIR"
fi

cd "$SOURCE_DIR"

# ==================== 依赖检查 ====================
echo ""
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
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    MISSING_APT="$MISSING_APT docker-compose-v2"
    MISSING_YUM="$MISSING_YUM docker-compose-plugin"
    MISSING_CMD="$MISSING_CMD docker-compose"
fi
if ! command -v python3 &> /dev/null; then
    MISSING_APT="$MISSING_APT python3"
    MISSING_YUM="$MISSING_YUM python3"
    MISSING_CMD="$MISSING_CMD python3"
fi
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    MISSING_APT="$MISSING_APT python3-pip"
    MISSING_YUM="$MISSING_YUM python3-pip"
    MISSING_CMD="$MISSING_CMD pip3"
fi

if [ -n "$MISSING_CMD" ]; then
    echo "    ✗ 发现缺失基础命令:$MISSING_CMD"
    prompt_input "    是否尝试自动一次性安装缺失的基础环境? (y/n) [y]: " install_deps_now "y"
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
            ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose 2>/dev/null || true
            ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/bin/docker-compose 2>/dev/null || true
        fi
        
        # 验证是否全部安装成功
        if ! command -v docker &> /dev/null || ! command -v python3 &> /dev/null; then
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
        prompt_input "    是否尝试启动 Docker 服务? (y/n) [y]: " start_docker_now "y"
        if [ "$start_docker_now" = "y" ]; then
            echo "    正在启动 Docker 服务..."
            if systemctl start docker; then
                echo "    ✓ Docker 服务已启动"
                systemctl enable docker &>/dev/null || true
            else
                echo "    ✗ Docker 服务启动失败，请检查: systemctl status docker"
                check_passed=false
            fi
        else
            check_passed=false
        fi
    fi
fi

# 检查 1Panel/OpenResty
echo "[2] 检查 1Panel/OpenResty..."
ONEPANEL_INSTALLED=false
if [ -d "/opt/1panel" ]; then
    ONEPANEL_INSTALLED=true
    echo "    ✓ 1Panel 已安装: /opt/1panel"
    
    if [ -d "/opt/1panel/apps/openresty/openresty/conf" ]; then
        echo "    ✓ OpenResty 已安装"
    else
        echo "    ! OpenResty 未安装（建议在 1Panel 应用商店中搜索并安装 OpenResty）"
    fi
    
    if [ -d "/opt/1panel/apps/openresty/openresty/www/sites" ]; then
        echo "    ✓ 网站目录存在: /opt/1panel/apps/openresty/openresty/www/sites"
    else
        echo "    ! 网站目录不存在: /opt/1panel/apps/openresty/openresty/www/sites (将在 1Panel 中建站时自动创建)"
    fi
else
    echo "    ! 1Panel 未安装（如不需要与 1Panel 深度集成可忽略）"
fi

# 检查 Keycloak 容器
echo "[3] 检查 Keycloak..."
KEYCLOAK_RUNNING=""
if command -v docker &> /dev/null && docker ps &> /dev/null; then
    KEYCLOAK_RUNNING=$(docker ps --filter "name=keycloak" --format "{{.Names}}" | head -1)
    if [ -n "$KEYCLOAK_RUNNING" ]; then
        echo "    ✓ Keycloak 容器运行中: $KEYCLOAK_RUNNING"
    else
        KEYCLOAK_EXISTS=$(docker ps -a --filter "name=keycloak" --format "{{.Names}}" | head -1)
        if [ -n "$KEYCLOAK_EXISTS" ]; then
            echo "    ! Keycloak 容器存在但未运行: $KEYCLOAK_EXISTS"
            prompt_input "    是否尝试启动该容器? (y/n) [y]: " start_kc_now "y"
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
            prompt_input "    是否现在自动部署 Keycloak 容器? (y/n) [y]: " deploy_kc_now "y"
            if [ "$deploy_kc_now" = "y" ]; then
                echo ""
                echo "--- 部署 Keycloak 容器配置 ---"
                prompt_input "    选择数据库类型 (h2/postgres) [h2]: " kc_db_type "h2"
                prompt_input "    设置 Keycloak 管理员用户名 [admin]: " kc_admin_user "admin"
                prompt_input "    设置 Keycloak 管理员密码 [admin123]: " kc_admin_pass "admin123" "true"
                prompt_input "    设置 Keycloak 映射端口 [8080]: " kc_port "8080"
                
                kc_db_pass=""
                if [ "$kc_db_type" = "postgres" ]; then
                    prompt_input "    设置 PostgreSQL 数据库密码 [KcDbPassWord_2026]: " kc_db_pass "KcDbPassWord_2026" "true"
                fi
                
                echo "    正在调用 deploy_keycloak.sh 部署容器..."
                if bash "$SOURCE_DIR/deploy_keycloak.sh" "$kc_db_type" "$kc_admin_user" "$kc_admin_pass" "$kc_port" "$kc_db_pass"; then
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
    prompt_input "是否继续部署（忽略检查失败）? (y/n) [n]: " force_continue "n"
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
local_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
local_ip=${local_ip:-127.0.0.1}

# 自动探测运行中 Keycloak 容器的映射端口
kc_detected_port=""
if [ -n "$KEYCLOAK_RUNNING" ]; then
    kc_detected_port=$(docker port "$KEYCLOAK_RUNNING" 8080 2>/dev/null | head -n1 | cut -d':' -f2)
fi
kc_detected_port=${kc_detected_port:-${kc_port:-8080}}

default_kc_url="http://$local_ip:$kc_detected_port"

# Keycloak URL
prompt_input "Keycloak 服务地址 [$default_kc_url]: " KEYCLOAK_URL "$default_kc_url"
if [[ ! "$KEYCLOAK_URL" =~ ^https?:// ]]; then
    KEYCLOAK_URL="http://$KEYCLOAK_URL"
fi

# 验证 Keycloak URL 是否可访问
echo "    测试 Keycloak 连接 ($KEYCLOAK_URL)..."
if curl -s -o /dev/null -w "%{http_code}" "$KEYCLOAK_URL" --max-time 5 | grep -q "200\|302\|303\|307\|404"; then
    echo "    ✓ Keycloak URL 可访问"
else
    echo "    ! Keycloak URL 暂时无法访问（若容器刚启动请稍候）"
fi

# Keycloak Admin 用户名
default_kc_admin=${kc_admin_user:-admin}
prompt_input "Keycloak Admin 用户名 [$default_kc_admin]: " KEYCLOAK_ADMIN "$default_kc_admin"

# Keycloak Admin 密码
default_kc_pass=${kc_admin_pass:-}
if [ -n "$default_kc_pass" ]; then
    prompt_input "Keycloak Admin 密码 [使用自动部署时设置的密码]: " KEYCLOAK_PASSWORD "$default_kc_pass" "true"
else
    prompt_input "Keycloak Admin 密码 [admin123]: " KEYCLOAK_PASSWORD "admin123" "true"
fi

# Web 控制台端口
prompt_input "Web 控制台端口 [8088]: " WEB_PORT "8088"

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
    prompt_input "    是否使用其他端口? 输入新端口: " NEW_PORT "$WEB_PORT"
    WEB_PORT=${NEW_PORT:-$WEB_PORT}
fi

# Keycloak 容器名称
default_kc_container=${KEYCLOAK_RUNNING:-keycloak}
prompt_input "Keycloak 容器名称 [$default_kc_container]: " KEYCLOAK_CONTAINER "$default_kc_container"

# 1Panel API 端口
prompt_input "1Panel API 端口 [40455]: " ONEPANEL_PORT "40455"

# 1Panel API Key
prompt_input "1Panel API Key (如果不使用 API 自动建站可留空): " ONEPANEL_API_KEY ""

# Apple 主题安装选择
echo ""
echo "=== Apple 主题安装 ==="
prompt_input "是否安装 Apple 登录主题? (y/n) [n]: " INSTALL_THEME "n"

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

prompt_input "确认部署? (y/n) [y]: " confirm "y"
if [ "$confirm" != "y" ]; then
    echo "取消部署"
    exit 0
fi

# ==================== 开始部署 ====================
echo ""
echo "=== 开始部署 ==="

# 安装 Python 依赖
echo "[1] 智能检测并安装 Python 依赖 (flask, cryptography, requests)..."

# 判断 Python 版本，对 Python 3.6 (CentOS 7) 锁定免 Rust 编译的版本 <=3.3.2
CRYPTO_PKG="cryptography"
if python3 -c "import sys; sys.exit(0 if sys.version_info < (3, 7) else 1)" 2>/dev/null; then
    CRYPTO_PKG="cryptography<=3.3.2"
fi

# 1. 优先尝试系统包管理器直接安装已编译的二进制库 (CentOS / Debian / Ubuntu)
if command -v yum >/dev/null 2>&1; then
    yum install -y -q epel-release 2>/dev/null || true
    yum install -y -q python3-pip python3-flask python3-cryptography python3-requests 2>/dev/null || true
elif command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y -q python3-pip python3-flask python3-cryptography python3-requests 2>/dev/null || true
fi

# 2. pip 安装 / 补齐
pip3 install flask "$CRYPTO_PKG" requests -q 2>/dev/null || \
pip install flask "$CRYPTO_PKG" requests -q 2>/dev/null || \
pip3 install flask "$CRYPTO_PKG" requests --break-system-packages -q 2>/dev/null || \
python3 -m pip install flask "$CRYPTO_PKG" requests -q 2>/dev/null || \
pip3 install flask requests -q 2>/dev/null || true

# 3. 校验核心依赖 (flask 与 requests 必须具备)
if python3 -c "import flask, requests" 2>/dev/null; then
    if python3 -c "import cryptography" 2>/dev/null; then
        echo "    ✓ Python 核心与安全依赖已全部就绪 (flask, cryptography, requests)"
    else
        echo "    ✓ Python 核心依赖已就绪 (flask, requests，开启内置安全加密兼容)"
    fi
else
    echo "    ✗ 严重错误: Python 核心依赖安装失败！请在终端手动执行 'pip3 install flask requests' 后重试。"
    exit 1
fi

# 创建安装目录
echo "[2] 创建安装目录..."
mkdir -p "$INSTALL_DIR"
echo "    ✓ 目录已创建: $INSTALL_DIR"

# 复制文件
echo "[2] 复制项目文件..."
cp -f "$SOURCE_DIR/app.py" "$INSTALL_DIR/"
cp -rf "$SOURCE_DIR/static" "$INSTALL_DIR/"
cp -rf "$SOURCE_DIR/templates" "$INSTALL_DIR/"
cp -rf "$SOURCE_DIR/themes" "$INSTALL_DIR/" 2>/dev/null || true
cp -rf "$SOURCE_DIR/nginx-auth" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$SOURCE_DIR/deploy_keycloak.sh" "$INSTALL_DIR/" 2>/dev/null || true
echo "    ✓ 文件已复制"

# 尝试还原备份的加密密钥与站点数据
if [ -f "/tmp/keycloak_auth_manager_backup/encryption.key" ]; then
    echo "    检测到备份的加密密钥，正在还原..."
    cp /tmp/keycloak_auth_manager_backup/encryption.key "$INSTALL_DIR/"
fi
if [ -f "/tmp/keycloak_auth_manager_backup/data.json" ]; then
    echo "    检测到备份的站点数据文件，正在还原..."
    cp /tmp/keycloak_auth_manager_backup/data.json "$INSTALL_DIR/"
fi

# 写入用户本次确认的最新配置文件（始终以本次输入为准）
echo "[3] 创建/更新配置文件..."
cat > "$INSTALL_DIR/config.json" << CONFIG
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

if [ ! -f "$INSTALL_DIR/data.json" ]; then
    echo '{}' > "$INSTALL_DIR/data.json"
fi

# 获取当前 python3 实际可执行路径
PYTHON_BIN=$(command -v python3 2>/dev/null || echo "/usr/bin/python3")

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
ExecStart=$PYTHON_BIN $INSTALL_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE
echo "    ✓ 服务文件已创建"

# 启动服务
echo "[5] 启动服务..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME
sleep 2

# 检查状态
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "    ✓ 服务已启动"
else
    echo "    ! 服务启动失败，请检查: journalctl -u $SERVICE_NAME -n 20"
fi

# 自动放行防火墙端口
echo "[6] 检查并配置防火墙规则..."
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$WEB_PORT"/tcp >/dev/null 2>&1 || true
    echo "    ✓ UFW 防火墙已放行端口: $WEB_PORT"
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --add-port="$WEB_PORT"/tcp --permanent >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
    echo "    ✓ Firewalld 防火墙已放行端口: $WEB_PORT"
fi
if command -v iptables >/dev/null 2>&1; then
    iptables -C INPUT -p tcp --dport "$WEB_PORT" -j ACCEPT 2>/dev/null || \
    iptables -I INPUT -p tcp --dport "$WEB_PORT" -j ACCEPT 2>/dev/null || true
    echo "    ✓ iptables 防火墙已放行端口: $WEB_PORT"
fi

# [7] 安装 Apple 主题
if [ "$INSTALL_THEME" = "y" ]; then
    echo "[7] 安装 Apple 主题..."
    THEME_DIR="/opt/keycloak/themes/apple"
    mkdir -p "$THEME_DIR"
    if [ -d "$SOURCE_DIR/themes/apple" ]; then
        cp -r "$SOURCE_DIR/themes/apple"/* "$THEME_DIR"/ 2>/dev/null || true
        echo "    ✓ Apple 主题本地文件已保存"
        
        # 复制到 Keycloak 容器内部
        if docker ps --filter "name=^/${KEYCLOAK_CONTAINER}$" --format "{{.Names}}" | grep -q "^${KEYCLOAK_CONTAINER}$"; then
            echo "    正在复制主题到容器 $KEYCLOAK_CONTAINER..."
            docker exec "$KEYCLOAK_CONTAINER" mkdir -p /opt/keycloak/themes 2>/dev/null || true
            docker cp "$SOURCE_DIR/themes/apple" "$KEYCLOAK_CONTAINER":/opt/keycloak/themes/
            docker restart "$KEYCLOAK_CONTAINER" >/dev/null
            echo "    ✓ Apple 主题已成功安装到容器 $KEYCLOAK_CONTAINER 且已重启该容器"
        else
            echo "    ! 未检测到运行中的 Keycloak 容器 $KEYCLOAK_CONTAINER，无法自动复制主题到容器内。"
            echo "    请在 Keycloak 容器启动后手动执行此命令复制主题："
            echo "    docker cp $INSTALL_DIR/themes/apple $KEYCLOAK_CONTAINER:/opt/keycloak/themes/"
        fi
        echo "    说明: 导入后，请在 Keycloak Admin Console 的 Realm Settings -> Themes 中选择 Login Theme 为 'apple'。"
    else
        echo "    ! 本地主题文件不存在，跳过安装。"
    fi
fi

PUBLIC_IP=$(curl -s --connect-timeout 3 ifconfig.me || curl -s --connect-timeout 3 icanhazip.com || echo "YOUR_SERVER_IP")

echo ""
echo "=========================================="
echo "  🎉 Keycloak Auth Manager 部署完成！"
echo "=========================================="
echo ""
echo "访问地址: http://${PUBLIC_IP}:$WEB_PORT"
echo ""
echo "文件位置:"
echo "  程序目录: $INSTALL_DIR"
echo "  配置文件: $INSTALL_DIR/config.json"
echo "  数据文件: $INSTALL_DIR/data.json"
echo ""
echo "管理命令:"
echo "  查看状态: systemctl status $SERVICE_NAME"
echo "  重启服务: systemctl restart $SERVICE_NAME"
echo "  查看日志: journalctl -u $SERVICE_NAME -f"
echo "=========================================="
echo ""
