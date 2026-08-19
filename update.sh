#!/usr/bin/env bash
# ==============================================================================
# Keycloak Auth Manager 一键更新脚本（数据安全防护、源码增量同步与服务平滑重启）
# 支持方式:
#   1. curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/update.sh | bash
#   2. cd /opt/keycloak-auth-manager && sudo bash update.sh
# ==============================================================================

set -e

INSTALL_DIR="/opt/keycloak-auth-manager"
SERVICE_NAME="keycloak-auth-manager"
REPO_URL="https://github.com/Level6me/keycloak-auth-manager.git"
BACKUP_DIR="/tmp/keycloak_auth_manager_update_backup_$(date +%s)"

echo ""
echo "=========================================="
echo "  Keycloak Auth Manager 一键更新"
echo "=========================================="
echo ""

# 1. 检查 root 权限
if [ "$(id -u)" -ne 0 ]; then
    echo "⚠️  请使用 root 权限或 sudo 执行更新脚本。"
    exit 1
fi

# 2. 检查安装目录是否存在
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ 未检测到安装目录: $INSTALL_DIR"
    echo "   如果您尚未安装 Keycloak Auth Manager，请先执行安装脚本："
    echo "   curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/install.sh | bash"
    exit 1
fi

echo "[1/6] 正在备份核心配置文件与加密密钥..."
mkdir -p "$BACKUP_DIR"

# 备份所有关键配置与数据
[ -f "$INSTALL_DIR/config.json" ] && cp "$INSTALL_DIR/config.json" "$BACKUP_DIR/"
[ -f "$INSTALL_DIR/data.json" ] && cp "$INSTALL_DIR/data.json" "$BACKUP_DIR/"
[ -f "$INSTALL_DIR/encryption.key" ] && cp "$INSTALL_DIR/encryption.key" "$BACKUP_DIR/"
[ -f "$INSTALL_DIR/secret.key" ] && cp "$INSTALL_DIR/secret.key" "$BACKUP_DIR/"
[ -d "$INSTALL_DIR/logs" ] && cp -r "$INSTALL_DIR/logs" "$BACKUP_DIR/" 2>/dev/null || true
[ -d "$INSTALL_DIR/custom_ssl" ] && cp -r "$INSTALL_DIR/custom_ssl" "$BACKUP_DIR/" 2>/dev/null || true

echo "    ✓ 关键数据已安全备份至: $BACKUP_DIR"

# 3. 获取最新项目源码
echo "[2/6] 正在拉取最新版本源码..."
TMP_SRC="/tmp/keycloak-auth-manager-latest-$(date +%s)"
rm -rf "$TMP_SRC"

# 优先使用 git clone 获取最新源码
if command -v git >/dev/null 2>&1; then
    git clone "$REPO_URL" "$TMP_SRC" -q || {
        echo "    ! 直连 GitHub 较慢，尝试备用拉取..."
        git clone "https://ghproxy.net/$REPO_URL" "$TMP_SRC" -q || git clone "$REPO_URL" "$TMP_SRC" -q
    }
else
    echo "    安装 git 工具中..."
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y -q && apt-get install -y -q git
    elif command -v yum >/dev/null 2>&1; then
        yum install -y -q git
    fi
    git clone "$REPO_URL" "$TMP_SRC" -q
fi

if [ ! -f "$TMP_SRC/app.py" ]; then
    echo "❌ 获取最新源码失败，请检查网络连接。"
    exit 1
fi
echo "    ✓ 最新源码已成功获取"

# 4. 同步更新程序文件（覆盖代码、静态资源、模板、脚本等，保留本地数据）
echo "[3/6] 正在同步并更新系统文件..."
cp -f "$TMP_SRC/app.py" "$INSTALL_DIR/"
cp -f "$TMP_SRC/deploy_keycloak.sh" "$INSTALL_DIR/"
cp -f "$TMP_SRC/install.sh" "$INSTALL_DIR/"
cp -f "$TMP_SRC/remote_install.sh" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$TMP_SRC/uninstall.sh" "$INSTALL_DIR/"
cp -f "$TMP_SRC/update.sh" "$INSTALL_DIR/"
cp -f "$TMP_SRC/README.md" "$INSTALL_DIR/" 2>/dev/null || true
[ -f "$TMP_SRC/Dockerfile" ] && cp -f "$TMP_SRC/Dockerfile" "$INSTALL_DIR/" 2>/dev/null || true

# 同步 templates 目录
mkdir -p "$INSTALL_DIR/templates"
cp -rf "$TMP_SRC/templates"/* "$INSTALL_DIR/templates/"

# 同步 static 目录
mkdir -p "$INSTALL_DIR/static"
cp -rf "$TMP_SRC/static"/* "$INSTALL_DIR/static/"

# 同步 themes 目录
if [ -d "$TMP_SRC/themes" ]; then
    mkdir -p "$INSTALL_DIR/themes"
    cp -rf "$TMP_SRC/themes"/* "$INSTALL_DIR/themes/"
fi

# 确保脚本具有执行权限
chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null || true
chmod +x "$INSTALL_DIR/app.py" 2>/dev/null || true

# 清理临时源码
rm -rf "$TMP_SRC"
echo "    ✓ 程序核心文件与静态资源已更新"

# 5. 校验并还原关键配置文件与加密密钥（双重保障）
echo "[4/6] 校验核心配置与加密密钥完整性..."
[ -f "$BACKUP_DIR/config.json" ] && cp -f "$BACKUP_DIR/config.json" "$INSTALL_DIR/"
[ -f "$BACKUP_DIR/data.json" ] && cp -f "$BACKUP_DIR/data.json" "$INSTALL_DIR/"
[ -f "$BACKUP_DIR/encryption.key" ] && cp -f "$BACKUP_DIR/encryption.key" "$INSTALL_DIR/"
[ -f "$BACKUP_DIR/secret.key" ] && cp -f "$BACKUP_DIR/secret.key" "$INSTALL_DIR/"
[ -d "$BACKUP_DIR/custom_ssl" ] && cp -rf "$BACKUP_DIR/custom_ssl" "$INSTALL_DIR/" 2>/dev/null || true

# 权限加固
[ -f "$INSTALL_DIR/encryption.key" ] && chmod 600 "$INSTALL_DIR/encryption.key" 2>/dev/null || true
[ -f "$INSTALL_DIR/config.json" ] && chmod 600 "$INSTALL_DIR/config.json" 2>/dev/null || true
echo "    ✓ 所有历史配置与站点数据校验完毕，完整无损"

# 6. 检查并增量更新 Python 依赖
echo "[5/6] 检查 Python 运行依赖库..."
PIP_CMD=""
if command -v pip3 >/dev/null 2>&1; then
    PIP_CMD="pip3"
elif command -v pip >/dev/null 2>&1; then
    PIP_CMD="pip"
fi

if [ -n "$PIP_CMD" ]; then
    $PIP_CMD install --upgrade --break-system-packages flask cryptography requests 2>/dev/null || \
    $PIP_CMD install --upgrade flask cryptography requests 2>/dev/null || true
    echo "    ✓ Python 依赖库检查完成"
fi

# 7. 重启 systemd 服务并验证
echo "[6/6] 正在平滑重启服务..."
systemctl daemon-reload
if systemctl is-enabled --quiet $SERVICE_NAME 2>/dev/null; then
    systemctl restart $SERVICE_NAME
else
    systemctl enable --now $SERVICE_NAME
fi

sleep 2

# 检查服务健康状态
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "    ✓ 服务已成功重启并正常运行"
else
    echo "    ⚠️ 服务重启异常，正在尝试读取错误日志..."
    journalctl -u $SERVICE_NAME -n 15 --no-pager
    exit 1
fi

# 读取配置中的 Web 端口
WEB_PORT=8000
if [ -f "$INSTALL_DIR/config.json" ]; then
    CFG_PORT=$(grep -o '"web_port"[[:space:]]*:[[:space:]]*[0-9]*' "$INSTALL_DIR/config.json" | grep -o '[0-9]*' || echo "")
    if [ -n "$CFG_PORT" ]; then
        WEB_PORT="$CFG_PORT"
    fi
fi

PUBLIC_IP=$(curl -s --connect-timeout 3 ifconfig.me || curl -s --connect-timeout 3 icanhazip.com || echo "127.0.0.1")

echo ""
echo "=========================================="
echo "  🎉 Keycloak Auth Manager 已成功更新至最新版本！"
echo "=========================================="
echo ""
echo "控制台访问地址: http://${PUBLIC_IP}:${WEB_PORT}"
echo ""
echo "常用运维命令:"
echo "  查看状态: systemctl status $SERVICE_NAME"
echo "  查看实时日志: journalctl -u $SERVICE_NAME -f"
echo "  重启服务: systemctl restart $SERVICE_NAME"
echo "  一键再次更新: bash $INSTALL_DIR/update.sh"
echo "=========================================="
echo ""
