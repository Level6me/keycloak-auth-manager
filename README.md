# Keycloak Auth Manager

Keycloak Passkey 认证管理 Web 控制台，一键为网站添加 OAuth2 认证保护。

## 功能特性

- ✅ 一键创建 Keycloak OAuth2 Client
- ✅ 自动创建 oauth2-proxy 容器
- ✅ 自动配置 Nginx 反向代理认证
- ✅ 支持多域名管理
- ✅ 支持 Passkey (WebAuthn) 无密码认证
- ✅ 支持无 email 用户认证
- ✅ systemd 服务，开机自启
- ✅ 交互式部署，自动检查依赖

## 系统要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Docker | 20.0+ | 容器运行环境 |
| Python3 | 3.6+ | Web 控制台运行环境 |
| 1Panel | 最新版 | 网站管理面板 |
| OpenResty | 最新版 | Nginx 反代（通过 1Panel 安装） |
| Keycloak | 26.x | OAuth2 认证服务（需先配置 Passkey） |

## 一键部署

```bash
# 克隆项目
git clone https://gitee.com/singkong/keycloak-auth-manager.git

# 进入目录
cd keycloak-auth-manager

# 一键部署（自动检查依赖 + 交互式配置）
bash install.sh
```

部署时会自动检查：
- Docker 是否安装并运行
- Python3/pip3 是否安装
- 1Panel/OpenResty 是否安装
- Keycloak 容器是否运行
- 端口是否被占用
- Keycloak URL 是否可访问

交互式配置：
- Keycloak 服务地址
- Keycloak Admin 用户名/密码
- Web 控制台端口
- Keycloak 容器名称

## 部署完成后

```
访问地址: http://服务器IP:8088

文件位置:
  程序:   /opt/keycloak-auth-manager/app.py
  配置:   /opt/keycloak-auth-manager/config.json
  数据:   /opt/keycloak-auth-manager/data.json
  日志:   /opt/keycloak-auth-manager/app.log
```

## 服务管理

```bash
systemctl status keycloak-auth-manager    # 查看状态
systemctl restart keycloak-auth-manager   # 重启服务
systemctl stop keycloak-auth-manager      # 停止服务
journalctl -u keycloak-auth-manager -f    # 查看日志
```

## 使用方法

### 1. 准备工作

- 在 1Panel 创建网站（配置反向代理到目标服务）
- 确保 Keycloak 已配置 Passkey 认证流程
- 用户需在 Keycloak 注册 Passkey

### 2. 添加认证

1. 访问 Web 控制台 `http://服务器IP:8088`
2. 输入域名（如 `your-domain.com`）
3. 点击「添加认证」
4. 自动完成：
   - 创建 Keycloak Client
   - 创建 oauth2-proxy 容器
   - 配置 Nginx 认证

### 3. 验证

访问 `https://your-domain.com`，会跳转到 Keycloak 进行 Passkey 认证。

## 文件说明

| 文件 | 说明 |
|------|------|
| `app.py` | Flask 主程序 |
| `config.json` | 部署配置（Keycloak 信息） |
| `data.json` | 已配置域名数据 |
| `install.sh` | 一键部署脚本 |
| `uninstall.sh` | 卸载脚本 |
| `nginx-auth/` | Nginx 配置模板 |
| `templates/` | HTML 模板 |
| `static/` | CSS 样式 |

## 卸载

```bash
cd keycloak-auth-manager
bash uninstall.sh
```

可选择保留 `data.json` 配置备份。

## 技术架构

```
用户请求 → Nginx (auth_request) → oauth2-proxy → Keycloak (Passkey认证)
                                          ↓
                                    认证成功 → 返回原站内容
```

oauth2-proxy 配置：
- `USER_ID_CLAIM=preferred_username`（支持无 email 用户）
- `INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true`

## 注意事项

1. **Passkey 必须先注册**：用户需在 Keycloak 管理界面注册 Passkey 才能登录
2. **data.json 不要提交 Git**：包含 client_secret 等敏感信息
3. **端口冲突**：默认 8088 端口，如被占用会提示更换
4. **Keycloak 版本**：推荐 26.x，支持 Passkey 流程

## 常见问题

### Q: 认证后显示 500 错误？

确保 oauth2 容器配置了 `USER_ID_CLAIM=preferred_username`。

### Q: 认证后显示 400 错误？

检查 Nginx 配置，某些后端（如 Home Assistant）不能发送 X-Forwarded-Proto header。

### Q: Passkey 登录没反应？

检查 Keycloak WebAuthn Policy RpId 是否与域名匹配。

## License

MIT

## 仓库

- Gitee（私有）: https://gitee.com/singkong/keycloak-auth-manager
