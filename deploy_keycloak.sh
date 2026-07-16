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

# 停止并删除已存在的同名容器
docker rm -f keycloak 2>/dev/null || true

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
        -e KEYCLOAK_ADMIN="$ADMIN_USER" \
        -e KEYCLOAK_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        -e KC_DB=postgres \
        -e KC_DB_URL=jdbc:postgresql://keycloak-db/keycloak \
        -e KC_DB_USERNAME=keycloak \
        -e KC_DB_PASSWORD="$DB_PASSWORD" \
        -e KC_PROXY_HEADERS=xforwarded \
        -e KC_HTTP_ENABLED=true \
        quay.io/keycloak/keycloak:26.1.0 \
        start
else
    echo "启动 Keycloak 容器 (开发模式，内置 H2)..."
    docker run -d \
        --name keycloak \
        --restart always \
        -p "$PORT":8080 \
        -e KEYCLOAK_ADMIN="$ADMIN_USER" \
        -e KEYCLOAK_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        -e KC_PROXY_HEADERS=xforwarded \
        -e KC_HTTP_ENABLED=true \
        quay.io/keycloak/keycloak:26.1.0 \
        start-dev
fi

echo "=== Keycloak 部署指令已发送 ==="
echo "等待 Keycloak 启动..."
# 检查端口是否可访问
for i in {1..30}; do
    if curl -s -I http://localhost:"$PORT" | grep -q "HTTP/1.1 200\|HTTP/1.1 302\|HTTP/1.1 303\|HTTP/1.1 307\|HTTP/1.1 404"; then
        echo "Keycloak 已成功运行在端口 $PORT !"
        break
    fi
    echo -n "."
    sleep 3
done

echo ""
echo "部署完成！"
echo "访问地址: http://<服务器IP>:$PORT"
echo "用户名: $ADMIN_USER"
echo "密码: [已设置的密码]"
