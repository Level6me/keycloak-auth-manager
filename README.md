# Keycloak Auth Manager (SSO & Passkey 管理中心)

一款专为现代化自建服务打造的 **企业级 Keycloak OAuth2 / OIDC 单点登录 (SSO) 与 Passkey (WebAuthn) 认证管理平台**。

通过轻量优雅的 Web 控制台，实现为 1Panel、OpenResty (Nginx) 托管的所有网站一键注入 **Apple 风格极简登录界面**、**全站单点登录免登 (Global SSO)**、**Passkey 免密生物识别直通** 及 **站点级精细化访问控制**。

---

## 🌟 核心特性与功能详解

### 1. 🚀 全局自适应单点登录 (Global SSO)
- **单容器全域复用**：彻底告别“一个站点起一个 oauth2-proxy 容器”的高开销模式，全局统一复用单一高可用 `oauth2-proxy-sso` 容器，极大节约服务器内存与系统端口。
- **根域级 Cookie 共享**：智能提取并计算顶级根域名（如 `.yourdomain.com`），用户只需在任意站点登录一次，旗下所有关联子站点（如 `wiki.yourdomain.com`、`git.yourdomain.com`）均享有一键自动免登。
- **动态白名单重定向防劫持**：严格过滤与校验 OIDC 重定向白名单，杜绝 Open Redirect 安全隐患。

### 2. 🍎 极简 Apple 风格登录体验
- **原生优雅视觉**：基于 Apple 人机交互设计规范，采用高通透纯白底色（`#ffffff`）、`24px` 舒适大圆角与微悬浮柔和阴影，与 Keycloak 原生结构无缝融合。
- **52px 饱满控件与无缝对齐**：输入框与主操作按钮统一采用 `52px` 黄金交互高度与 `14px` 细腻圆角。
- **眼睛显隐按钮内嵌无框贴合**：密码查看图标完全内嵌于密码框右侧且无任何多余方框边框，密码栏与用户名栏实现 100% 完全等长对齐。

### 3. 🔑 Passkey (WebAuthn) 免密直通与手势直拉
- **当前页面直接拉起生物识别**：密码登录页点击「使用 Passkey 登录」时，直接在当前用户手势（User Gesture）内调起系统原生的 Face ID / Touch ID / Windows Hello / YubiKey / Android 生物识别，无需二次跳转中间选择页，秒级进入系统。
- **按站点独立控制认证策略 (Per-Site Auth Policy)**：
  - **纯 Passkey 模式（关闭密码认证）**：访问该站点时，直接呈现纯净的 Passkey 免密卡片，彻底隐藏密码表单及入口，禁止通过密码绕过。
  - **纯密码模式（关闭 Passkey 认证）**：访问该站点时，仅显示干净的账号密码登录框，完全隐藏 Passkey 链接与入口。
  - **混合免密模式（两者皆开启）**：同时支持账号密码输入与一键直通 Passkey 免密登录，兼顾便捷与兼容。
- **毫秒级策略同步**：控制台修改站点登录方式后，自动生成 `site-policy.json` 注入 Keycloak 主题，无需重启容器，毫秒级全局生效且零跨域阻碍。

### 4. 🌐 1Panel & OpenResty & Cloudflare 深度生态联动
- **1Panel 站点自动感知**：自动识别本地 1Panel 部署目录与 OpenResty 站点，自动生成 `auth_request` 保护配置并无缝安全重载。
- **Cloudflare DNS 与 IP 智能集成**：支持自动获取并同步公网 IP、Cloudflare API Token 联动、代理状态切换。
- **一键申请与自动续期 SSL 证书**：支持一键检查与签发证书，全链路强制 HTTPS 加密保护。

### 5. 👥 用户管理与站点访问细粒度授权
- **可视化用户面板**：在 Web 控制台内直接查看、搜索与管理 Keycloak Realm 用户列表。
- **多站点授权白名单 (`allowed_sites`)**：支持针对特定用户授予指定站点的访问权限，未授权用户在登录通过后将被拦截在受限页面之外。
- **用户运维操作**：支持快速重置密码、修改用户信息、启用/禁用账号及分配权限角色。

### 6. 🛡️ 企业级安全性与安全防护
- **敏感凭据落盘加密**：基于 Fernet (AES-128-CBC + HMAC-SHA256) 算法对配置文件中的所有 API Token、Client Secret、Cookie Secret 进行落盘强加密保护。
- **防暴力破解速率限制**：内置控制台登录滑动窗口限流防刷算法，防范自动化密码碰撞与暴力破解。
- **防路径遍历白名单**：严格对域名参数进行正则表达式白名单校验，杜绝路径穿越写入攻击。
- **系统日志脱敏**：敏感凭证输出时自动过滤脱敏，避免因日志收集导致密钥泄露。

---

## 🛠️ 系统架构

```
                   ┌───────────────────────────────────────────────┐
                   │               用户终端 / 客户端                │
                   └───────────────────────┬───────────────────────┘
                                           │
                                    HTTPS 请求 (443)
                                           │
                                           ▼
                   ┌───────────────────────────────────────────────┐
                   │             OpenResty / Nginx 反代            │
                   │    (执行 auth_request 拦截，未认证 302 @login)   │
                   └───────┬───────────────────────────────▲───────┘
                           │                               │
                      内部校验 (4180)                  验证通过放行
                           │                               │
                           ▼                               │
                   ┌───────────────────────────────┐       │
                   │      oauth2-proxy-sso 容器     │       │
                   │   (全局单一实例，共享 Root Cookie) │       │
                   └───────┬───────────────────────┘       │
                           │                               │
                       OIDC 重定向                         │
                           │                               │
                           ▼                               │
                   ┌───────────────────────────────────────────────┐
                   │            Keycloak 26.x 认证服务             │
                   │  - Apple 极简卡片主题                           │
                   │  - 动态站点策略 site-policy.json                 │
                   │  - Face ID / Touch ID / WebAuthn 直通认证      │
                   └───────────────────────────────────────────────┘
```

---

## 💻 快速部署与安装

### 方式一：远程一键全自动部署（推荐）

```bash
curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/install.sh | bash
```

### 方式二：源码克隆部署

```bash
# 1. 克隆代码仓库
git clone https://github.com/Level6me/keycloak-auth-manager.git

# 2. 进入目录并执行安装向导
cd keycloak-auth-manager
bash install.sh
```

> **安装向导将全自动检测并完成**：
> - Docker 运行状态与端口占用检测；
> - 1Panel / OpenResty 与 Keycloak 容器联通性校验；
> - 交互式配置 Keycloak API 访问凭证、控制台端口与 1Panel 集成密钥；
> - 自动创建 systemd 服务并设置开机自启。

---

## 🔄 无损平滑更新

所有升级过程均会自动保留 `config.json`（服务配置）、`data.json`（站点代理数据）与 `encryption.key`（加密密钥）：

```bash
# 远程一键无损更新
curl -sSL https://raw.githubusercontent.com/Level6me/keycloak-auth-manager/main/update.sh | bash
```

---

## 🧭 服务管理指令

```bash
systemctl status keycloak-auth-manager    # 查看控制台运行状态
systemctl restart keycloak-auth-manager   # 重启控制台服务
systemctl stop keycloak-auth-manager      # 停止服务
journalctl -u keycloak-auth-manager -f    # 实时查看控制台日志
```

---

## 📋 文件目录说明

| 文件 / 路径 | 说明 |
| :--- | :--- |
| `app.py` | 后端核心服务（Flask Web 控制台、API 接口与自动化策略控制器） |
| `themes/apple/` | 苹果风格极简 Keycloak 主题（含 CSS 样式、直通脚本与策略配置） |
| `templates/` | 控制台前端页面模板（站点列表、用户权限、SSL 与系统配置） |
| `static/` | 控制台前端静态资源（JavaScript 交互逻辑与样式表） |
| `config.json` | 系统核心运行配置（加密保存凭据信息） |
| `data.json` | 代理站点数据列表与多站点策略配置 |
| `encryption.key` | 本地凭据落盘加密专用密钥 |
| `install.sh` | 交互式环境检测与一键部署脚本 |
| `update.sh` | 保留配置的无损一键热更新脚本 |
| `uninstall.sh` | 安全卸载脚本（支持备份数据） |

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
