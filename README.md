# Keycloak Auth Manager - 网站认证与单点登录管理中心

Keycloak Auth Manager 是一款专为站长、开发者与运维人员打造的 **现代化 Web 访问控制与单点登录 (SSO) 管理控制台**。

通过轻量直观的 Web 控制台，为服务器上的任意网站快速接入身份验证拦截保护、全站单点登录与多模式认证策略。

---

## 🖥️ 控制面板核心功能

### 1. 一键为网站添加访问认证
只需输入网站访问域名与后端目标服务端口，即可全自动完成建站、反向代理配置与身份验证保护接入。

### 2. 全站单点登录 (SSO)
登录旗下任意一个子域名，同主域名下的其他站点自动实现免密直通，无需在每个网站重复输入凭据。

### 3. Passkey (WebAuthn) 免密直接拉起
点击「使用 Passkey 登录」直接在当前页面调起设备原生的**指纹、Face ID、Windows Hello 或硬件安全密钥**，秒级完成免密验证。

### 4. 三种认证模式按需切换
每个站点可根据安全要求独立设置认证策略：
- **纯 Passkey 认证**：进入登录页直接调起并呈现极简免密认证卡片，前端彻底隐藏账号密码输入框与切换入口，提供纯粹的免密直通体验；
- **纯密码认证**：仅显示传统的账号密码登录框，完全不展示 Passkey 入口；
- **混合认证**：同时支持账号密码输入与一键直通 Passkey 免密登录，兼顾不同设备与使用习惯。

### 5. 用户与多站点权限管理
在控制台内直接管理 Keycloak 账号（新建用户、一键重置密码、账号启用/禁用），并支持**按用户设置可访问的站点白名单 (`allowed_sites`)**，未授权用户登录后将自动被拦截。

### 6. Cloudflare 域名智能联动
自动拉取 Cloudflare 托管的主域名列表，添加站点时可自动配置 DNS A 记录解析，并支持一键开启或关闭 CDN 代理加速。

---

## 📦 系统依赖与运行环境

| 依赖程序 | 推荐版本 | 作用说明 |
| :--- | :--- | :--- |
| **Docker** | 20.0+ | 容器运行基础环境，用于部署 SSO 代理服务与目标网站容器 |
| **Python 3 / pip3** | 3.6+ | 控制面板后台（Flask）的运行环境 |
| **Keycloak** | 26.x | 核心身份认证服务中心，提供用户账号体系、OAuth2/OIDC 认证与 Passkey 支持 |
| **1Panel 面板** | 最新版 | 网站建站管理面板，用于自动化网站创建与配置联动 |
| **OpenResty (Nginx)** | 最新版 | 高性能 Web 反向代理，通过 `auth_request` 模块实现流量拦截与身份验证（通过 1Panel 安装） |
| **Cloudflare** *(可选)* | API Token | 用于实现域名 DNS 解析自动绑定与 CDN 代理联动（可选配置） |

---

## 🚀 快速安装与使用

### 方式一：远程一键全自动部署（推荐）

在服务器终端执行以下命令，脚本将自动检查环境依赖并启动配置向导：

```bash
curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/install.sh | bash
```

### 方式二：克隆源码部署

```bash
git clone https://github.com/Level6me/keycloak-auth-manager.git
cd keycloak-auth-manager
bash install.sh
```

### 部署完成后访问

- **控制台地址**：`http://你的服务器IP:8088`
- **默认管理员账号**：安装向导中设定的账号与密码

---

## 🔄 一键平滑更新

更新过程会自动保留现有的所有站点数据（`data.json`）、系统配置（`config.json`）与加密密钥（`encryption.key`），实现无损热升级：

```bash
curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/update.sh | bash
```

---

## 🧭 服务管理常用命令

```bash
systemctl status keycloak-auth-manager    # 查看服务运行状态
systemctl restart keycloak-auth-manager   # 重启控制台服务
systemctl stop keycloak-auth-manager      # 停止控制台服务
journalctl -u keycloak-auth-manager -f    # 实时查看运行日志
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
