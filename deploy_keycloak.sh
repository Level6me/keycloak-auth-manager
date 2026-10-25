#!/bin/bash
# deploy_keycloak.sh - Deploy Keycloak container automatically

set -e

DB_TYPE=$1
ADMIN_USER=$2
ADMIN_PASSWORD=$3
PORT=$4
DB_PASSWORD=$5

if [ -z "$DB_TYPE" ] || [ -z "$ADMIN_USER" ] || [ -z "$ADMIN_PASSWORD" ] || [ -z "$PORT" ]; then
    echo "Usage: $0 <h2|postgres> <admin_user> <admin_password> <port> [db_password]"
    exit 1
fi

echo "=== 开始部署 Keycloak 容器 ==="
echo "数据库类型: $DB_TYPE"
echo "管理员用户: $ADMIN_USER"
echo "映射端口: $PORT"

# 0. 自动检测并启用 2GB Swap 虚拟内存（防止低内存 VPS 发生 OOM-killer 崩溃）
if [ -f /proc/meminfo ] && [ -w / ]; then
    swap_total=$(free -m 2>/dev/null | awk '/Swap:/ {print $2}' || echo "0")
    if [ "${swap_total:-0}" -lt 512 ] && [ ! -f /swapfile ]; then
        echo "检测到系统未配置 Swap，正在自动创建 2GB 虚拟内存以保障 Keycloak 稳定运行..."
        dd if=/dev/zero of=/swapfile bs=1M count=2048 2>/dev/null || true
        if [ -f /swapfile ]; then
            chmod 600 /swapfile
            mkswap /swapfile >/dev/null 2>&1 || true
            swapon /swapfile 2>/dev/null || true
            if ! grep -q "/swapfile" /etc/fstab 2>/dev/null; then
                echo '/swapfile none swap sw 0 0' >> /etc/fstab
            fi
            echo "✓ 2GB Swap 虚拟内存已就绪"
        fi
    fi
fi

# 停止并删除已存在的同名容器
docker rm -f keycloak 2>/dev/null || true

# 预先创建挂载目录并赋予 Keycloak 容器用户 (UID 1000) 读写权限，防止权限拒绝导致崩溃循环
mkdir -p /opt/keycloak/data /opt/keycloak/themes
chown -R 1000:1000 /opt/keycloak/data /opt/keycloak/themes 2>/dev/null || true
chmod -R 775 /opt/keycloak/data /opt/keycloak/themes 2>/dev/null || true

if [ "$DB_TYPE" = "postgres" ]; then
    if [ -z "$DB_PASSWORD" ]; then
        DB_PASSWORD="YOUR_DB_PASSWORD_HERE"
    fi
    
    echo "创建 Docker 网络..."
    docker network create keycloak-net 2>/dev/null || true
    
    echo "启动 PostgreSQL 数据库容器..."
    docker rm -f keycloak-db 2>/dev/null || true
    docker run -d \
        --name keycloak-db \
        --network keycloak-net \
        --restart always \
        -v keycloak-db-data:/var/lib/postgresql/data \
        -e POSTGRES_DB=keycloak \
        -e POSTGRES_USER=keycloak \
        -e POSTGRES_PASSWORD="$DB_PASSWORD" \
        postgres:16
        
    echo "等待 PostgreSQL 启动..."
    for i in {1..30}; do
        if docker exec keycloak-db pg_isready -U keycloak -d keycloak &>/dev/null; then
            echo "PostgreSQL 已就绪！"
            break
        fi
        echo -n "."
        sleep 2
    done
    
    echo "启动 Keycloak 容器 (生产模式)..."
    docker run -d \
        --name keycloak \
        --network keycloak-net \
        --restart always \
        -p "$PORT":8080 \
        -v /opt/keycloak/data:/opt/keycloak/data \
        -v /opt/keycloak/themes:/opt/keycloak/themes \
        -e KEYCLOAK_ADMIN="$ADMIN_USER" \
        -e KEYCLOAK_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        -e KC_DB=postgres \
        -e KC_DB_URL=jdbc:postgresql://keycloak-db/keycloak \
        -e KC_DB_USERNAME=keycloak \
        -e KC_DB_PASSWORD="$DB_PASSWORD" \
        -e KC_PROXY_HEADERS=xforwarded \
        -e KC_HTTP_ENABLED=true \
        -e JAVA_OPTS_APPEND="-Xms256m -Xmx768m -XX:MaxMetaspaceSize=384m -XX:+UseG1GC -Djava.awt.headless=true" \
        quay.io/keycloak/keycloak:26.1.0 \
        start
else
    echo "启动 Keycloak 容器 (开发模式，内置 H2)..."
    echo "⚠️ 警告: start-dev 为开发模式，不适合生产环境（性能受限且重启即重置引导态）。生产部署请选择 postgres 模式。"
    docker run -d \
        --name keycloak \
        --restart always \
        -p "$PORT":8080 \
        -v /opt/keycloak/data:/opt/keycloak/data \
        -v /opt/keycloak/themes:/opt/keycloak/themes \
        -e KEYCLOAK_ADMIN="$ADMIN_USER" \
        -e KEYCLOAK_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        -e KC_PROXY_HEADERS=xforwarded \
        -e KC_HTTP_ENABLED=true \
        -e KC_SPI_THEME_DEFAULT_CACHE_THEMES=true \
        -e KC_SPI_THEME_DEFAULT_CACHE_TEMPLATES=true \
        -e KC_SPI_THEME_DEFAULT_STATIC_MAX_AGE=2592000 \
        -e JAVA_OPTS_APPEND="-Xms256m -Xmx768m -XX:MaxMetaspaceSize=384m -XX:+UseG1GC -Djava.awt.headless=true" \
        quay.io/keycloak/keycloak:26.1.0 \
        start-dev --spi-theme-static-max-age=2592000 --spi-theme-cache-themes=true --spi-theme-cache-templates=true
fi

echo "=== Keycloak 部署指令已发送 ==="
echo "等待 Keycloak 启动..."
# 严格健康检查：仅 200/重定向视为成功，404 不算就绪；超时则报错退出（修复健康检查形同虚设）
kc_ready=false
for i in {1..40}; do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -qE "^(200|302|303|307)$"; then
        echo ""
        echo "Keycloak 已成功运行在端口 $PORT !"
        kc_ready=true
        break
    fi
    echo -n "."
    sleep 3
done

if [ "$kc_ready" != "true" ]; then
    echo ""
    echo "❌ 部署失败：Keycloak 在预期时间内未就绪，请执行 docker logs keycloak 排查"
    exit 1
fi

echo ""
echo "部署完成！"
echo "访问地址: http://<服务器IP>:$PORT"
echo "用户名: $ADMIN_USER"
echo "密码: [已设置的密码]"
