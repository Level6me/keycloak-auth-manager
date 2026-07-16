# Keycloak Apple 主题

Apple 风格的 Keycloak 登录主题，支持 Passkey 无密码认证。

## 安装方法

### 方法1：挂载目录（推荐）

```bash
# 复制主题到服务器
mkdir -p /opt/keycloak/themes/apple
cp -r themes/apple/login /opt/keycloak/themes/apple/

# 重启 Keycloak 容器（如果主题目录已挂载）
docker restart keycloak
```

### 方法2：容器内复制

```bash
# 将主题复制到容器内
docker cp themes/apple/login keycloak:/opt/keycloak/themes/apple/

# 不需要重启，Keycloak 自动检测新主题
```

## 使用方法

1. 登录 Keycloak Admin Console
2. Realm Settings → Themes
3. Login Theme 选择 `apple`
4. 保存

## 主题特性

- Apple 风格 UI 设计
- Passkey 按钮居中显示
- 简洁的登录界面
- 自定义 Apple Logo

## 文件说明

```
apple/login/
├── theme.properties    # 主题配置
└── resources/
    ├── css/styles.css  # 样式文件
    └── img/apple-logo.svg  # Apple Logo
```
