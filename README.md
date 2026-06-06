# Keycloak Auth Manager

Keycloak Passkey 认证管理 Web 控制台，用于快速为网站添加 Keycloak OAuth2 认证保护。

## 功能

- 一键创建 Keycloak Client
- 自动创建 oauth2-proxy 容器
- 自动配置 Nginx 反向代理认证
- 支持多域名管理
- 支持 Passkey (WebAuthn) 无密码认证

## 依赖

- Keycloak 26.x (已配置 Passkey 认证)
- oauth2-proxy v7.6.0
- 1Panel + OpenResty (Nginx)
- Docker

## 环境要求

- Keycloak 容器名称: `keycloak`
- Keycloak admin 账号: `admin` / `keycloak2026`
- Keycloak URL: 配置环境变量 `KEYCLOAK_URL`

## 一键部署

```bash
# 克隆项目
git clone https://gitee.com/singkong/keycloak-auth-manager.git

# 进入目录
cd keycloak-auth-manager

# 安装依赖
pip3 install flask

# 启动服务
python3 app.py
```

## Docker 部署

```bash
docker build -t keycloak-auth-manager .
docker run -d -p 8088:8088 --name auth-manager \
    -v /opt/1panel/apps/openresty/openresty/www/sites:/www/sites \
    --network host \
    keycloak-auth-manager
```

## 使用方法

1. 先在 1Panel 创建网站（配置反向代理）
2. 访问 Web 控制台 (默认端口 8088)
3. 输入域名，点击"添加认证"
4. 自动创建 Keycloak Client + oauth2-proxy + Nginx 配置

## 配置说明

- `data.json`: 存储已配置的域名信息（敏感，不要提交）
- `nginx-auth/`: Nginx 认证配置模板

## 注意事项

- 用户需要在 Keycloak 中注册 Passkey 才能登录
- oauth2-proxy 配置支持无 email 用户 (USER_ID_CLAIM=preferred_username)
- Nginx 需要 proxy_buffer 配置处理大量 cookie

## License

MIT

## 一键部署（推荐）

```bash
# 克隆项目
git clone https://gitee.com/singkong/keycloak-auth-manager.git

# 进入目录
cd keycloak-auth-manager

# 一键部署（自动安装为 systemd 服务）
bash install.sh
```

部署完成后：
- 服务地址: `http://服务器IP:8088`
- 日志文件: `/opt/keycloak-auth-manager/app.log`
- 配置文件: `/opt/keycloak-auth-manager/data.json`

## 服务管理

```bash
systemctl status keycloak-auth-manager   # 查看状态
systemctl restart keycloak-auth-manager  # 重启服务
systemctl stop keycloak-auth-manager     # 停止服务
journalctl -u keycloak-auth-manager -f   # 查看日志
```

## 卸载

```bash
cd keycloak-auth-manager
bash uninstall.sh
```
