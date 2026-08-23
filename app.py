#!/usr/bin/env python3
import os, json, subprocess, secrets, string, time, re, hashlib, requests, threading, base64
import concurrent.futures
from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context, send_from_directory, session, jsonify
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict
import shlex
import copy

# 全局高性能 HTTP 连接池 Session（复用 TCP/TLS 保持长连接，大幅降低 Keycloak REST API 往返延迟）
_HTTP_SESSION = requests.Session()
_HTTP_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=100, max_retries=1)
_HTTP_SESSION.mount('http://', _HTTP_ADAPTER)
_HTTP_SESSION.mount('https://', _HTTP_ADAPTER)

# 配置文件路径

CONFIG_FILE = "/opt/keycloak-auth-manager/config.json"
DATA_FILE = "/opt/keycloak-auth-manager/data.json"
ENCRYPTION_KEY_FILE = "/opt/keycloak-auth-manager/encryption.key"

# 加密模块加载（支持 Fernet，缺失时安全回退，防止崩溃）
CIPHER_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    if not os.path.exists(ENCRYPTION_KEY_FILE):
        os.makedirs('/opt/keycloak-auth-manager', exist_ok=True)
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        try:
            os.chmod(ENCRYPTION_KEY_FILE, 0o600)
        except Exception:
            pass

    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            fernet_key = f.read().strip()
        cipher = Fernet(fernet_key)
        CIPHER_AVAILABLE = True
except Exception as e:
    print(f"提示: cryptography 模块未就绪 ({e})，使用内置兼容模式。")

def encrypt_val(val):
    if not val: return ""
    if CIPHER_AVAILABLE:
        try:
            return cipher.encrypt(val.encode('utf-8')).decode('utf-8')
        except Exception as e:
            print("加密失败:", str(e))
            return val
    return val

def decrypt_val(val):
    if not val: return ""
    if CIPHER_AVAILABLE:
        try:
            return cipher.decrypt(val.encode('utf-8')).decode('utf-8')
        except Exception as e:
            return val
    return val

# 配置变量（从 config.json 加载，无默认值）
KEYCLOAK_URL = ""
KEYCLOAK_ADMIN = ""
KEYCLOAK_PASSWORD = ""
KEYCLOAK_CONTAINER = "keycloak"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = ""
ONEPANEL_API_KEY = ""
ONEPANEL_PORT = 40455
WEB_PORT = 8088
CLOUDFLARE_API_TOKEN = ""
CLOUDFLARE_SERVER_IP = ""
CLOUDFLARE_PROXIED = False

_CACHED_PUBLIC_IP = None
_CACHED_PUBLIC_IP_TIME = 0

# ─── 漏洞#10 修复：登录速率限制（防暴力破解）───
_login_fail_lock = threading.Lock()
_login_fail_records = defaultdict(list)   # {ip: [timestamp, ...]}
LOGIN_RATE_WINDOW = 300   # 5 分钟滑动窗口
LOGIN_RATE_MAX_FAIL = 10  # 窗口内最多失败 10 次

def _get_client_ip():
    """获取真实客户端 IP（兼容反代场景）"""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

def _is_rate_limited(ip):
    now = time.time()
    with _login_fail_lock:
        records = _login_fail_records[ip]
        # 清理过期记录
        _login_fail_records[ip] = [t for t in records if now - t < LOGIN_RATE_WINDOW]
        return len(_login_fail_records[ip]) >= LOGIN_RATE_MAX_FAIL

def _record_fail(ip):
    now = time.time()
    with _login_fail_lock:
        _login_fail_records[ip].append(now)

def _reset_fail(ip):
    with _login_fail_lock:
        _login_fail_records.pop(ip, None)

# ─── 漏洞#11 修复：域名格式白名单正则（防路径遍历 → 任意文件写入）───
DOMAIN_RE = re.compile(r'^[a-z0-9]([a-z0-9\-\.]{0,253}[a-z0-9])?$')

def is_valid_domain(domain):
    """严格校验域名格式，防止路径遍历攻击"""
    if not domain or '..' in domain or '/' in domain or '\\' in domain:
        return False
    return bool(DOMAIN_RE.match(domain))


def get_server_public_ip():
    global _CACHED_PUBLIC_IP, _CACHED_PUBLIC_IP_TIME
    if CLOUDFLARE_SERVER_IP and CLOUDFLARE_SERVER_IP.strip():
        return CLOUDFLARE_SERVER_IP.strip()
    now = time.time()
    if _CACHED_PUBLIC_IP and (now - _CACHED_PUBLIC_IP_TIME < 300):
        return _CACHED_PUBLIC_IP
    ip_services = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com"
    ]
    for s in ip_services:
        try:
            r = requests.get(s, timeout=3)
            if r.status_code == 200:
                ip = r.text.strip()
                if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
                    _CACHED_PUBLIC_IP = ip
                    _CACHED_PUBLIC_IP_TIME = now
                    return ip
        except Exception:
            continue
    return ""

def run_cmd_args(args):
    # 安全地以列表形式调用命令，不经过 Shell
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.returncode, r.stdout, r.stderr

def load_config():
    global KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_CONTAINER
    global ADMIN_USERNAME, ADMIN_PASSWORD
    global WEB_PORT, ONEPANEL_API_KEY, ONEPANEL_PORT
    global CLOUDFLARE_API_TOKEN, CLOUDFLARE_SERVER_IP, CLOUDFLARE_PROXIED
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            
            raw_password = cfg.get("keycloak_password", "")
            raw_console_user = cfg.get("console_username", "admin").strip()
            raw_console_pwd = cfg.get("console_password", "")
            raw_api_key = cfg.get("onepanel_api_key", "")
            raw_cf_token = cfg.get("cloudflare_api_token", "")
            
            KEYCLOAK_PASSWORD = decrypt_val(raw_password)
            ADMIN_USERNAME = raw_console_user or "admin"
            if raw_console_pwd:
                ADMIN_PASSWORD = decrypt_val(raw_console_pwd)
            elif KEYCLOAK_PASSWORD:
                ADMIN_PASSWORD = KEYCLOAK_PASSWORD
            else:
                # 若未单独配置密码，尝试从运行中的 Keycloak 容器环境变量嗅探初始管理员密码
                try:
                    rc_env, out_env, _ = run_cmd_args(["docker", "inspect", cfg.get("keycloak_container", "keycloak"), "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
                    if rc_env == 0 and out_env:
                        for line in out_env.splitlines():
                            if line.startswith("KC_BOOTSTRAP_ADMIN_PASSWORD=") or line.startswith("KEYCLOAK_ADMIN_PASSWORD="):
                                ADMIN_PASSWORD = line.split("=", 1)[1].strip()
                                break
                except Exception:
                    ADMIN_PASSWORD = ""

            ONEPANEL_API_KEY = decrypt_val(raw_api_key)
            CLOUDFLARE_API_TOKEN = decrypt_val(raw_cf_token)
            CLOUDFLARE_SERVER_IP = cfg.get("cloudflare_server_ip", "")
            CLOUDFLARE_PROXIED = bool(cfg.get("cloudflare_proxied", False))
            
            need_rewrite = False
            if raw_password and not raw_password.startswith("gAAAA"):
                cfg["keycloak_password"] = encrypt_val(raw_password)
                need_rewrite = True
            if raw_console_pwd and not raw_console_pwd.startswith("gAAAA"):
                cfg["console_password"] = encrypt_val(raw_console_pwd)
                need_rewrite = True
            if raw_api_key and not raw_api_key.startswith("gAAAA"):
                cfg["onepanel_api_key"] = encrypt_val(raw_api_key)
                need_rewrite = True
            if raw_cf_token and not raw_cf_token.startswith("gAAAA"):
                cfg["cloudflare_api_token"] = encrypt_val(raw_cf_token)
                need_rewrite = True
                
            raw_url = cfg.get("keycloak_url", "").strip()
            if raw_url:
                if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                    raw_url = "https://" + raw_url
                raw_url = raw_url.rstrip("/")
            KEYCLOAK_URL = raw_url
            KEYCLOAK_ADMIN = cfg.get("keycloak_admin", "")
            KEYCLOAK_CONTAINER = cfg.get("keycloak_container", "keycloak")
            WEB_PORT = cfg.get("web_port", 8088)
            ONEPANEL_PORT = cfg.get("onepanel_port", 40455)
            
            if need_rewrite:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(cfg, f, indent=2)
                try:
                    os.chmod(CONFIG_FILE, 0o600)
                except Exception:
                    pass
    except Exception as e:
        print("加载配置失败:", str(e))

load_config()

app = Flask(__name__)
# 修复：使用固定的或持久化的 secret_key，并加异常保护防止目录不存在时崩溃
try:
    if not os.path.exists('/opt/keycloak-auth-manager/secret.key'):
        os.makedirs('/opt/keycloak-auth-manager', exist_ok=True)
        with open('/opt/keycloak-auth-manager/secret.key', 'w') as f:
            f.write(secrets.token_hex(32))
    with open('/opt/keycloak-auth-manager/secret.key', 'r') as f:
        app.secret_key = f.read().strip()
except Exception as e:
    print(f"警告: 无法读取持久化 secret_key，使用随机密钥 ({e})")
    app.secret_key = secrets.token_hex(32)

@app.after_request
def set_csrf_cookie(response):
    """将 CSRF token 设置为非 HttpOnly Cookie，供前端 JS 读取并在 POST 请求中附带（Double Submit Cookie 模式）"""
    if session.get('logged_in') and session.get('csrf_token'):
        response.set_cookie(
            'csrf_token',
            session['csrf_token'],
            samesite='Strict',
            httponly=False,   # 必须允许 JS 读取才能实现 Double Submit Cookie
            secure=False      # 生产环境建议改为 True（需要 HTTPS）
        )
    return response

@app.before_request
def check_auth():
    # 静态资源与认证白名单
    allowed_paths = ['/login', '/static', '/favicon.ico', '/favicon.svg']
    if any(request.path == p or request.path.startswith(p + '/') or request.path.startswith('/static/') for p in allowed_paths):
        return None

    # ─── 漏洞#1 修复：无密码时禁止所有写操作（POST/PUT/DELETE），GET 只读允许 ───
    if not ADMIN_PASSWORD:
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            if request.path.startswith('/api/'):
                return Response(json.dumps({"success": False, "error": "控制台尚未设置密码，写操作已禁用，请先前往 /settings 设置控制台密码", "code": 403}),
                                status=403, mimetype="application/json")
            flash("⚠️ 安全警告：控制台尚未设置管理密码，所有写操作已禁用。请立即前往「系统设置」页面设置密码。", "danger")
            return redirect(url_for('settings'))
        # 未设密码时 GET 只读请求仍然放行（便于首次配置）
        return None

    # 检查 session 登录态
    if session.get('logged_in') and session.get('user') == ADMIN_USERNAME:
        # ─── 漏洞#9 修复：POST 写操作强制校验 CSRF token ───
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            session_token = session.get('csrf_token', '')
            form_token = (request.form.get('_csrf_token', '') or
                          request.headers.get('X-CSRF-Token', '') or
                          request.get_json(silent=True, force=True) and request.get_json(silent=True, force=True).get('_csrf_token', '') or '')
            if not session_token or session_token != form_token:
                if request.path.startswith('/api/'):
                    return Response(json.dumps({"success": False, "error": "CSRF token 校验失败，请刷新页面后重试", "code": 403}),
                                    status=403, mimetype="application/json")
                flash("请求校验失败，请刷新页面后重试", "danger")
                return redirect(url_for('index'))
        return None

    # 检查 HTTP Basic Auth（支持自动化脚本，同样受速率限制保护）
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        client_ip = _get_client_ip()
        if _is_rate_limited(client_ip):
            return Response(json.dumps({"success": False, "error": "登录尝试过于频繁，请 5 分钟后再试", "code": 429}),
                            status=429, mimetype="application/json")
        try:
            auth_decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            u, p = auth_decoded.split(":", 1)
            if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
                _reset_fail(client_ip)
                session['logged_in'] = True
                session['user'] = ADMIN_USERNAME
                if 'csrf_token' not in session:
                    session['csrf_token'] = secrets.token_hex(32)
                return None
            else:
                _record_fail(client_ip)
        except Exception:
            pass

    if request.path.startswith('/api/'):
        return Response(json.dumps({"success": False, "error": "未授权访问，请先登录控制台", "code": 401}),
                        status=401, mimetype="application/json")

    return redirect(url_for('login_page', next=request.path))

def _safe_redirect_url(next_url):
    """漏洞#2 修复：安全过滤重定向 URL，防止 Open Redirect"""
    if not next_url:
        return '/'
    parsed = urlparse(next_url)
    # 拒绝含有 scheme 或 netloc 的 URL（如 //evil.com、https://evil.com、/\evil.com）
    if parsed.scheme or parsed.netloc:
        return '/'
    # 必须以 / 开头且不含换行符（防 Header Injection）
    if not next_url.startswith('/') or '\n' in next_url or '\r' in next_url:
        return '/'
    return next_url

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        client_ip = _get_client_ip()
        # ─── 漏洞#10 修复：速率限制检查 ───
        if _is_rate_limited(client_ip):
            flash("登录尝试过于频繁，请 5 分钟后再试", "danger")
            return render_template('login.html', username='', csrf_token=session.get('csrf_token', ''))

        user = request.form.get('username', '').strip()
        pwd = request.form.get('password', '').strip()
        next_url = _safe_redirect_url(request.args.get('next', '/'))

        if not ADMIN_PASSWORD or (user == ADMIN_USERNAME and pwd == ADMIN_PASSWORD):
            _reset_fail(client_ip)
            session['logged_in'] = True
            session['user'] = ADMIN_USERNAME
            # 生成会话级 CSRF token
            session['csrf_token'] = secrets.token_hex(32)
            flash("登录成功", "success")
            return redirect(next_url)
        else:
            _record_fail(client_ip)
            flash("用户名或密码错误", "danger")
            return render_template('login.html', username=user, csrf_token='')

    if session.get('logged_in') and session.get('user') == ADMIN_USERNAME:
        return redirect('/')
    # 确保 session 中有 csrf_token
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return render_template('login.html', username=ADMIN_USERNAME, csrf_token=session.get('csrf_token', ''))

@app.route('/logout')
def logout():
    session.clear()
    flash("已成功退出登录", "success")
    return redirect(url_for('login_page'))


# 线程安全且支持断点重连的日志缓冲区
MAX_LOG_HISTORY = 500
log_history = []
log_seq = 0
logs_lock = threading.Lock()

def check_domain_ssl_enabled(domain):
    if not domain:
        return False
    domain = domain.strip().lower()
    
    # 1. 检查 conf.d/ 下的站点主配置文件中是否配置并启用了 SSL
    conf_paths = [
        f"/opt/1panel/apps/openresty/openresty/conf/conf.d/{domain}.conf",
        f"/opt/1panel/conf/conf.d/{domain}.conf",
        f"/etc/nginx/conf.d/{domain}.conf"
    ]
    for p in conf_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if 'ssl_certificate' in content or ('listen' in content and '443' in content and 'ssl' in content):
                    return True
            except Exception:
                pass

    # 2. 检查站点目录下的 ssl/ 证书文件是否存在且非空
    ssl_paths = [
        f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}/ssl/fullchain.pem",
        f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}/ssl/cert.pem",
        f"/opt/1panel/www/sites/{domain}/ssl/fullchain.pem",
        f"/opt/1panel/www/sites/{domain}/ssl/cert.pem"
    ]
    for p in ssl_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return True

    # 3. 若配置了 1Panel API Key，通过 API 实时查询 HTTPS 开启状态
    if ONEPANEL_API_KEY:
        try:
            ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
            if ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]:
                ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
                if ws_item and ws_item.get("protocol", "").upper() == "HTTPS":
                    return True
        except Exception:
            pass

    return False

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            changed = False
            for domain, auth in data.items():
                if isinstance(auth, dict):
                    if 'client_secret' in auth:
                        auth['client_secret'] = decrypt_val(auth['client_secret'])
                    if 'cookie_secret' in auth:
                        auth['cookie_secret'] = decrypt_val(auth['cookie_secret'])
                    
                    # 默认状态注入与向前兼容
                    if 'target_host' not in auth:
                        auth['target_host'] = '127.0.0.1'
                    if 'target_port' not in auth:
                        t_port = auth.get('port')
                        if not t_port:
                            proxy_conf = get_proxy_conf_path(domain)
                            if proxy_conf and os.path.exists(proxy_conf):
                                try:
                                    with open(proxy_conf, 'r') as pf:
                                        content = pf.read()
                                    oauth_port = str(auth.get('oauth_port', 4180))
                                    matches = re.findall(r'proxy_pass http://([^:/;\s]+):([0-9]+);', content)
                                    for h, p in matches:
                                        if p != oauth_port:
                                            auth['target_host'] = h
                                            t_port = int(p)
                                            break
                                except Exception:
                                    pass
                        auth['target_port'] = t_port or 80
                        changed = True

                    if 'proxy_enabled' not in auth:
                        auth['proxy_enabled'] = True
                    if 'auth_enabled' not in auth:
                        auth['auth_enabled'] = True
                        
                    # 动态精确校准 SSL 开启状态
                    real_ssl = check_domain_ssl_enabled(domain)
                    if auth.get('ssl_enabled') != real_ssl:
                        auth['ssl_enabled'] = real_ssl
                        changed = True
            if changed:
                save_data(data)
            return data
        except Exception as e:
            print("加载数据失败:", str(e))
    return {}

def save_data(data):
    write_data = copy.deepcopy(data)
    for domain, auth in write_data.items():
        if isinstance(auth, dict):
            if 'client_secret' in auth:
                auth['client_secret'] = encrypt_val(auth['client_secret'])
            if 'cookie_secret' in auth:
                auth['cookie_secret'] = encrypt_val(auth['cookie_secret'])
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(write_data, f, indent=2)
        try:
            os.chmod(DATA_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        print("保存数据失败:", str(e))

def generate_secret(length=32):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def log(msg):
    global log_seq
    line = "[{}] {}".format(datetime.now().strftime("%H:%M:%S"), msg)
    with logs_lock:
        log_seq += 1
        entry = {"id": log_seq, "text": line}
        log_history.append(entry)
        if len(log_history) > MAX_LOG_HISTORY:
            log_history.pop(0)
    print(line)

def clear_logs():
    global log_history
    with logs_lock:
        log_history.clear()

def get_used_ports():
    ports = set()
    # 优先使用 ss（现代 Linux 标准工具），若不存在则回退到 netstat
    rc, out, err = run_cmd_args(["ss", "-tlnp"])
    if rc != 0:
        rc, out, err = run_cmd_args(["netstat", "-tlnp"])
    if rc == 0:
        for line in out.splitlines():
            # 匹配所有本地绑定的监听端口
            matches = re.findall(r':(\d+)\s+', line)
            for m in matches:
                try:
                    ports.add(int(m))
                except ValueError:
                    pass
    
    # 额外检查 data.json 中已经分配出去的端口（防止容器崩溃时释放端口导致重复分配）
    data = load_data()
    for k, v in data.items():
        if isinstance(v, dict) and 'oauth_port' in v:
            try:
                ports.add(int(v['oauth_port']))
            except (ValueError, TypeError):
                pass
            
    return ports

def call_1panel_api(endpoint, method="POST", payload=None):
    if not ONEPANEL_API_KEY:
        log("警告: 未配置 1Panel API Key，跳过 API 调用")
        return None

    # 规范化分页与排序参数，严格兼容 1Panel 接口约束
    req_payload = payload
    if isinstance(payload, dict):
        req_payload = dict(payload)
        for old_k, new_k in [("Page", "page"), ("PageSize", "pageSize"), ("OrderBy", "orderBy"), ("Order", "order"), ("Info", "info")]:
            if old_k in req_payload and new_k not in req_payload:
                req_payload[new_k] = req_payload.pop(old_k)
        if "page" in req_payload and "pageSize" in req_payload:
            req_payload.setdefault("orderBy", "created_at")
            req_payload.setdefault("order", "null")

    ts = str(int(time.time()))
    token = hashlib.md5(("1panel" + ONEPANEL_API_KEY + ts).encode()).hexdigest()
    headers = {
        "1Panel-Token": token,
        "1Panel-Timestamp": ts,
        "Content-Type": "application/json"
    }

    # 优先使用 1Panel v1 端点，如遇 404 或安全入口 HTML 拦截则自动降级/切换
    endpoints_to_try = [endpoint]
    if endpoint.startswith("/api/v2/"):
        endpoints_to_try.insert(0, endpoint.replace("/api/v2/", "/api/v1/"))
    elif endpoint.startswith("/api/v1/"):
        endpoints_to_try.append(endpoint.replace("/api/v1/", "/api/v2/"))

    for ep in endpoints_to_try:
        url = f"http://127.0.0.1:{ONEPANEL_PORT}{ep}"
        try:
            if method == "POST":
                res = requests.post(url, headers=headers, json=req_payload, timeout=10)
            else:
                res = requests.get(url, headers=headers, params=req_payload, timeout=10)
            
            # 若返回 HTML (通常为 404 或安全入口拦截)，继续尝试下一个兼容端点
            if res.status_code == 200 and res.text.strip().startswith("<!DOCTYPE"):
                continue
            if res.status_code == 404:
                continue
            return res.json()
        except Exception as e:
            if ep == endpoints_to_try[-1]:
                log(f"1Panel API 错误 ({ep}): {e}")
    return None

def get_cloudflare_zones():
    if not CLOUDFLARE_API_TOKEN:
        return []
    url = "https://api.cloudflare.com/client/v4/zones?status=active&per_page=50"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if data.get("success") and data.get("result"):
            zones = []
            for z in data["result"]:
                zones.append({
                    "id": z.get("id"),
                    "name": z.get("name"),
                    "status": z.get("status")
                })
            return zones
        else:
            err_msg = data.get("errors", [{}])[0].get("message", "未知错误") if data.get("errors") else "请求失败"
            log(f"获取 Cloudflare Zones 失败: {err_msg}")
            return []
    except Exception as e:
        log(f"获取 Cloudflare Zones 异常: {e}")
        return []

def add_or_update_cloudflare_dns(full_domain, server_ip=None, proxied=None):
    if not CLOUDFLARE_API_TOKEN:
        return False, "未配置 Cloudflare API Token"
    
    full_domain = full_domain.strip().lower()
    if not full_domain:
        return False, "域名为空"
        
    zones = get_cloudflare_zones()
    if not zones:
        return False, "未能获取到 Cloudflare Zone 列表，请检查 Token 权限"
        
    matched_zone = None
    for z in zones:
        z_name = z["name"].lower()
        if full_domain == z_name or full_domain.endswith("." + z_name):
            if not matched_zone or len(z_name) > len(matched_zone["name"]):
                matched_zone = z
                
    if not matched_zone:
        return False, f"在 Cloudflare 中未找到与域名 {full_domain} 匹配的 Zone 托管区域"
        
    zone_id = matched_zone["id"]
    zone_name = matched_zone["name"]
    
    target_ip = (server_ip or "").strip() or get_server_public_ip()
    if not target_ip:
        return False, "无法获取服务器公网 IP，请在设置中指定或手动输入"
        
    is_proxied = CLOUDFLARE_PROXIED if proxied is None else bool(proxied)
    
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    log(f"[Cloudflare DNS] 正在自动配置 A 记录: {full_domain} -> {target_ip} (Zone: {zone_name}, Proxy: {is_proxied})")
    
    try:
        query_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=A&name={full_domain}"
        res = requests.get(query_url, headers=headers, timeout=10)
        data = res.json()
        
        if not data.get("success"):
            err_msg = data.get("errors", [{}])[0].get("message", "查询记录失败") if data.get("errors") else "查询失败"
            log(f"[Cloudflare DNS] 查询 DNS 记录失败: {err_msg}")
            return False, f"Cloudflare API: {err_msg}"
            
        records = data.get("result", [])
        if records:
            rec = records[0]
            rec_id = rec["id"]
            if rec.get("content") == target_ip and rec.get("proxied") == is_proxied:
                log(f"[Cloudflare DNS] A 记录已存在且完全匹配 (IP: {target_ip}, Proxy: {is_proxied})，无需修改。")
                return True, ""
                
            update_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{rec_id}"
            payload = {
                "type": "A",
                "name": full_domain,
                "content": target_ip,
                "ttl": 1,
                "proxied": is_proxied,
                "comment": "Managed by Auth Manager"
            }
            up_res = requests.put(update_url, headers=headers, json=payload, timeout=10)
            up_data = up_res.json()
            if up_data.get("success"):
                log(f"[Cloudflare DNS] 成功更新 A 记录: {full_domain} -> {target_ip}")
                return True, ""
            else:
                err_msg = up_data.get("errors", [{}])[0].get("message", "更新失败") if up_data.get("errors") else "更新失败"
                log(f"[Cloudflare DNS] 更新 A 记录失败: {err_msg}")
                return False, f"Cloudflare API: {err_msg}"
        else:
            create_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
            payload = {
                "type": "A",
                "name": full_domain,
                "content": target_ip,
                "ttl": 1,
                "proxied": is_proxied,
                "comment": "Managed by Auth Manager"
            }
            cr_res = requests.post(create_url, headers=headers, json=payload, timeout=10)
            cr_data = cr_res.json()
            if cr_data.get("success"):
                log(f"[Cloudflare DNS] 成功创建 A 记录: {full_domain} -> {target_ip}")
                return True, ""
            else:
                err_msg = cr_data.get("errors", [{}])[0].get("message", "创建失败") if cr_data.get("errors") else "创建失败"
                log(f"[Cloudflare DNS] 创建 A 记录失败: {err_msg}")
                return False, f"Cloudflare API: {err_msg}"
                
    except Exception as e:
        log(f"[Cloudflare DNS] API 请求发生异常: {e}")
        return False, str(e)

_KC_CREDS_CACHE = {"data": None, "expires_at": 0}
_KC_CREDS_LOCK = threading.Lock()

def get_keycloak_admin_credentials(force_refresh=False):
    global KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_URL, KEYCLOAK_CONTAINER, _KC_CREDS_CACHE
    now = time.time()
    with _KC_CREDS_LOCK:
        if not force_refresh and _KC_CREDS_CACHE["data"] and now < _KC_CREDS_CACHE["expires_at"]:
            return _KC_CREDS_CACHE["data"]

        admin_user = KEYCLOAK_ADMIN
        admin_pass = KEYCLOAK_PASSWORD
        kc_url = KEYCLOAK_URL

        # 优先从本地已保存的 config.json 中读取
        if not admin_pass or not kc_url:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r') as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            if not admin_user:
                admin_user = cfg.get("keycloak_admin", "admin")
            if not admin_pass:
                admin_pass = decrypt_val(cfg.get("keycloak_password", ""))
            if not kc_url:
                kc_url = cfg.get("keycloak_url", "")

        container_user = ""
        container_pass = ""
        container_host = ""
        try:
            rc, out, _ = run_cmd_args(["docker", "inspect", KEYCLOAK_CONTAINER, "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
            if rc == 0 and out:
                env_map = {}
                for line in out.strip().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_map[k.strip()] = v.strip()
                container_user = env_map.get("KC_BOOTSTRAP_ADMIN_USERNAME") or env_map.get("KEYCLOAK_ADMIN") or "admin"
                container_pass = env_map.get("KC_BOOTSTRAP_ADMIN_PASSWORD") or env_map.get("KEYCLOAK_ADMIN_PASSWORD") or ""
                container_host = env_map.get("KC_HOSTNAME", "")
        except Exception:
            pass

        if not admin_pass:
            admin_pass = container_pass
        if not admin_user:
            admin_user = container_user or "admin"
        if not kc_url and container_host:
            kc_url = container_host

        if not kc_url:
            kc_url = "http://127.0.0.1:8080"

        if not kc_url.startswith("http://") and not kc_url.startswith("https://"):
            kc_url = "https://" + kc_url
        kc_url = kc_url.rstrip("/")

        res = (admin_user or "admin", admin_pass or "", kc_url)
        _KC_CREDS_CACHE["data"] = res
        _KC_CREDS_CACHE["expires_at"] = now + 300 # 缓存 5 分钟
        return res

# ─── Keycloak Admin REST API 统一封装与 Token 缓存 ───
_KC_TOKEN_CACHE = {"token": None, "expires_at": 0, "base": None}
_KC_TOKEN_LOCK = threading.Lock()

def get_keycloak_admin_token(force_refresh=False):
    global _KC_TOKEN_CACHE, _KC_CREDS_CACHE, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD
    now = time.time()
    with _KC_TOKEN_LOCK:
        if not force_refresh and _KC_TOKEN_CACHE["token"] and (now < _KC_TOKEN_CACHE["expires_at"]):
            return _KC_TOKEN_CACHE["token"], _KC_TOKEN_CACHE["base"]
            
        admin_user, admin_pass, kc_base = get_keycloak_admin_credentials()
        
        # 收集所有可能的管理员账号密码组合（按优先级排列）
        cred_candidates = []
        if admin_user and admin_pass:
            cred_candidates.append((admin_user, admin_pass))
            
        # 提取容器内的 Bootstrap 环境变量作为保底候选
        try:
            rc, out, _ = run_cmd_args(["docker", "inspect", KEYCLOAK_CONTAINER, "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
            if rc == 0 and out:
                env_map = {}
                for line in out.strip().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_map[k.strip()] = v.strip()
                c_user = env_map.get("KC_BOOTSTRAP_ADMIN_USERNAME") or env_map.get("KEYCLOAK_ADMIN") or "admin"
                c_pass = env_map.get("KC_BOOTSTRAP_ADMIN_PASSWORD") or env_map.get("KEYCLOAK_ADMIN_PASSWORD") or ""
                if c_user and c_pass and (c_user, c_pass) not in cred_candidates:
                    cred_candidates.append((c_user, c_pass))
                if c_pass and ("admin", c_pass) not in cred_candidates:
                    cred_candidates.append(("admin", c_pass))
        except Exception:
            pass

        if admin_pass and ("admin", admin_pass) not in cred_candidates:
            cred_candidates.append(("admin", admin_pass))

        if not cred_candidates:
            return None, None
            
        # 优先使用本地极速回路 127.0.0.1:8080，避免公网回路和 DNS 解析延迟
        endpoints = ["http://127.0.0.1:8080"]
        if kc_base and kc_base not in endpoints:
            endpoints.append(kc_base)
            
        token = None
        active_base = None
        working_user = None
        working_pass = None
        
        for base in endpoints:
            if token:
                break
            for u, p in cred_candidates:
                token_url = f"{base}/realms/master/protocol/openid-connect/token"
                try:
                    res = _HTTP_SESSION.post(token_url, data={
                        "client_id": "admin-cli",
                        "username": u,
                        "password": p,
                        "grant_type": "password"
                    }, timeout=3)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("access_token")
                        expires_in = data.get("expires_in", 60)
                        if token:
                            active_base = base
                            working_user = u
                            working_pass = p
                            _KC_TOKEN_CACHE["token"] = token
                            _KC_TOKEN_CACHE["expires_at"] = now + max(10, expires_in - 10)
                            _KC_TOKEN_CACHE["base"] = active_base
                            # 记录并持久化已验证通过的正确凭据
                            _KC_CREDS_CACHE["data"] = (working_user, working_pass, kc_base)
                            _KC_CREDS_CACHE["expires_at"] = now + 600
                            break
                except Exception:
                    continue
                
        return token, active_base


def call_keycloak_api(endpoint, method="GET", json_data=None, params=None):
    token, base = get_keycloak_admin_token()
    if not token or not base:
        token, base = get_keycloak_admin_token(force_refresh=True)
        if not token or not base:
            return None, 500, "无法连接 Keycloak Admin API，请检查管理员密码与容器运行状态"
            
    url = f"{base}/admin/realms/master/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    try:
        if method == "GET":
            res = _HTTP_SESSION.get(url, headers=headers, params=params, timeout=5)
        elif method == "POST":
            res = _HTTP_SESSION.post(url, headers=headers, json=json_data, timeout=5)
        elif method == "PUT":
            res = _HTTP_SESSION.put(url, headers=headers, json=json_data, timeout=5)
        elif method == "DELETE":
            res = _HTTP_SESSION.delete(url, headers=headers, timeout=5)
        else:
            return None, 400, f"不支持的 HTTP 方法: {method}"
            
        if res.status_code == 401:
            token, base = get_keycloak_admin_token(force_refresh=True)
            if token and base:
                url = f"{base}/admin/realms/master/{endpoint.lstrip('/')}"
                headers["Authorization"] = f"Bearer {token}"
                if method == "GET":
                    res = _HTTP_SESSION.get(url, headers=headers, params=params, timeout=5)
                elif method == "POST":
                    res = _HTTP_SESSION.post(url, headers=headers, json=json_data, timeout=5)
                elif method == "PUT":
                    res = _HTTP_SESSION.put(url, headers=headers, json=json_data, timeout=5)
                elif method == "DELETE":
                    res = _HTTP_SESSION.delete(url, headers=headers, timeout=5)

        data = None
        if res.text:
            try:
                data = res.json()
            except Exception:
                data = res.text
        return data, res.status_code, ""
    except Exception as e:
        return None, 500, str(e)


def ensure_keycloak_user_profile_allowed_sites():
    """确保 Keycloak 启用了非托管自定义属性 (unmanagedAttributePolicy) 并注册 allowed_sites 属性支持"""
    try:
        up, code, _ = call_keycloak_api("users/profile", "GET")
        if code == 200 and isinstance(up, dict):
            modified = False
            if up.get("unmanagedAttributePolicy") != "ENABLED":
                up["unmanagedAttributePolicy"] = "ENABLED"
                modified = True
            attrs_list = up.get("attributes", [])
            if not any(a.get("name") == "allowed_sites" for a in attrs_list):
                attrs_list.append({
                    "name": "allowed_sites",
                    "displayName": "Allowed Sites",
                    "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
                    "multivalued": True
                })
                up["attributes"] = attrs_list
                modified = True
            if modified:
                call_keycloak_api("users/profile", "PUT", json_data=up)
                log("Keycloak 用户属性规范已成功注册 allowed_sites 存储支持！")
    except Exception as e:
        log(f"配置 Keycloak 用户属性规范异常: {e}")

def setup_keycloak_adaptive_sso_flow():
    token, active_base = get_keycloak_admin_token()
    if not token or not active_base:
        log("提示: 暂未连接到 Keycloak API (可忽略)，跳过自适应认证流配置")
        return None

    try:
        # 1. 确保 Keycloak User Profile 允许保存 allowed_sites
        ensure_keycloak_user_profile_allowed_sites()

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        api_base = f"{active_base}/admin/realms/master"
        auth_api = f"{api_base}/authentication"

        # 2. 强制注册时绑定 Passkey Required Action
        req_actions_url = f"{auth_api}/required-actions"
        actions_res = requests.get(req_actions_url, headers=headers, timeout=6)
        if actions_res.status_code == 200:
            for action in actions_res.json():
                if action.get("alias") == "webauthn-register-passwordless":
                    action["enabled"] = True
                    action["defaultAction"] = True
                    requests.put(f"{req_actions_url}/{action['alias']}", headers=headers, json=action, timeout=6)
                    break

        # 3. 创建/校验 passkey-only-browser 流
        flows = requests.get(f"{auth_api}/flows", headers=headers, timeout=6).json()
        if not isinstance(flows, list):
            flows = []

        pk_flow = next((f for f in flows if f.get("alias") == "passkey-only-browser"), None)
        if not pk_flow:
            requests.post(f"{auth_api}/flows", headers=headers, json={
                "alias": "passkey-only-browser",
                "providerId": "basic-flow",
                "topLevel": True,
                "builtIn": False,
                "description": "Auth manager passkey only flow"
            }, timeout=6)
            requests.post(f"{auth_api}/flows/passkey-only-browser/executions/execution", headers=headers, json={"provider": "auth-cookie"}, timeout=6)
            requests.post(f"{auth_api}/flows/passkey-only-browser/executions/execution", headers=headers, json={"provider": "webauthn-authenticator-passwordless"}, timeout=6)
            for ex in requests.get(f"{auth_api}/flows/passkey-only-browser/executions", headers=headers, timeout=6).json():
                ex["requirement"] = "ALTERNATIVE"
                requests.put(f"{auth_api}/flows/passkey-only-browser/executions", headers=headers, json=ex, timeout=6)

        # 4. 创建/更新 global-sso-browser 流 (Cookie + Forms + Passkey 混合免密模式，杜绝 400 错误与多余重复项)
        flows = requests.get(f"{auth_api}/flows", headers=headers, timeout=6).json()
        if not isinstance(flows, list):
            flows = []

        existing_global_flow = next((f for f in flows if f.get("alias") == "global-sso-browser"), None)
        if existing_global_flow:
            cur_execs = requests.get(f"{auth_api}/flows/global-sso-browser/executions", headers=headers, timeout=6).json()
            top_providers = [e.get("displayName") or e.get("providerId") for e in cur_execs if e.get("level") == 0]
            # 严格确保只有 3 个顶级项：Cookie、global-sso-forms、WebAuthn
            if len(top_providers) != 3 or any(e.get("requirement") == "CONDITIONAL" for e in cur_execs):
                requests.delete(f"{auth_api}/flows/{existing_global_flow['id']}", headers=headers, timeout=6)
                existing_global_flow = None

        if not existing_global_flow:
            requests.post(f"{auth_api}/flows", headers=headers, json={
                "alias": "global-sso-browser",
                "providerId": "basic-flow",
                "topLevel": True,
                "builtIn": False,
                "description": "Global SSO Multi-mode Adaptive Browser Flow"
            }, timeout=6)


            # 1. auth-cookie (ALTERNATIVE)
            requests.post(f"{auth_api}/flows/global-sso-browser/executions/execution", headers=headers, json={"provider": "auth-cookie"}, timeout=6)

            # 2. global-sso-forms (ALTERNATIVE)
            requests.post(f"{auth_api}/flows/global-sso-browser/executions/flow", headers=headers, json={
                "alias": "global-sso-forms",
                "type": "basic-flow",
                "provider": "registration-page-form",
                "description": "Username Password Form Subflow"
            }, timeout=6)
            requests.post(f"{auth_api}/flows/global-sso-forms/executions/execution", headers=headers, json={"provider": "auth-username-password-form"}, timeout=6)

            # 3. webauthn-authenticator-passwordless (ALTERNATIVE)
            requests.post(f"{auth_api}/flows/global-sso-browser/executions/execution", headers=headers, json={"provider": "webauthn-authenticator-passwordless"}, timeout=6)

            # 设置 requirement
            for ex in requests.get(f"{auth_api}/flows/global-sso-browser/executions", headers=headers, timeout=6).json():
                ex["requirement"] = "ALTERNATIVE"
                requests.put(f"{auth_api}/flows/global-sso-browser/executions", headers=headers, json=ex, timeout=6)

            for ex in requests.get(f"{auth_api}/flows/global-sso-forms/executions", headers=headers, timeout=6).json():
                ex["requirement"] = "REQUIRED"
                requests.put(f"{auth_api}/flows/global-sso-forms/executions", headers=headers, json=ex, timeout=6)

        flows = requests.get(f"{auth_api}/flows", headers=headers, timeout=6).json()
        target_flow = next((f for f in flows if f.get("alias") == "global-sso-browser"), None)
        if target_flow:
            return target_flow["id"]

        return None
    except Exception as e:
        log(f"配置 Keycloak 自适应认证流异常: {e}")
        return None


def setup_keycloak_passkey_flow():
    """兼容旧函数名别名"""
    return setup_keycloak_adaptive_sso_flow()


GLOBAL_SSO_PORT = 4180
GLOBAL_SSO_CLIENT_ID = "global-sso"
GLOBAL_SSO_CONTAINER = "oauth2-proxy-sso"

def get_root_domain(domain):
    """从域名中提取用于 SSO Cookie 共享的根域 (如 ips.abab.pw -> .abab.pw)"""
    if not domain:
        return ""
    domain = domain.strip().lower()
    parts = domain.split('.')
    if len(parts) >= 2:
        return "." + ".".join(parts[-2:])
    return "." + domain

def get_all_cookie_and_whitelist_domains(data=None, extra_domain=None):
    """计算所有站点所需的作用域 Cookie 域名和白名单域名"""
    if data is None:
        data = load_data()
    all_domains = list(data.keys())
    if extra_domain and extra_domain not in all_domains:
        all_domains.append(extra_domain)
        
    cookie_domains = set()
    whitelist_domains = set()
    
    for d in all_domains:
        d = d.strip().lower()
        if not d:
            continue
        rd = get_root_domain(d)
        if rd:
            cookie_domains.add(rd)
            whitelist_domains.add(f"*{rd}")
            whitelist_domains.add(rd.lstrip('.'))
            
    # 自动将 Keycloak 域名加入白名单，确保注销与切换账号跳转允许跨域重定向
    try:
        _, _, kc_url = get_keycloak_admin_credentials()
        if kc_url and "://" in kc_url:
            kc_host = kc_url.split("://", 1)[1].split("/")[0].split(":")[0].strip().lower()
            if kc_host:
                whitelist_domains.add(kc_host)
                kc_rd = get_root_domain(kc_host)
                if kc_rd:
                    whitelist_domains.add(f"*{kc_rd}")
                    whitelist_domains.add(kc_rd.lstrip('.'))
    except Exception:
        pass

    # 默认兜底
    if not cookie_domains:
        cookie_domains.add(".abab.pw")
        whitelist_domains.add("*.abab.pw")
        whitelist_domains.add("abab.pw")
        
    return ",".join(sorted(list(cookie_domains))), ",".join(sorted(list(whitelist_domains)))


def ensure_global_sso_client(client_secret=None, extra_domain=None):
    """确保 Keycloak 中存在通配且绑定 Passkey 认证流的全局 global-sso 客户端"""
    admin_user, admin_pass, kc_issuer_base = get_keycloak_admin_credentials()
    if not admin_pass:
        return False, "未获取到 Keycloak 管理员密码", ""
        
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
        except Exception:
            pass
            
    if not client_secret:
        raw_sec = cfg.get("global_sso_client_secret", "")
        if raw_sec:
            client_secret = decrypt_val(raw_sec)
            
    if not client_secret:
        client_secret = generate_secret(32)
        cfg["global_sso_client_secret"] = encrypt_val(client_secret)
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
            
    # 确保 Passkey 自定义认证流就绪
    passkey_flow_id = setup_keycloak_passkey_flow()
    
    # 构建所有站点的 Redirect URIs 列表（必须包含 * 通配与具体站点 callback 路径，保证 Keycloak 严格匹配）
    data = load_data()
    all_domains = list(data.keys())
    if extra_domain and extra_domain not in all_domains:
        all_domains.append(extra_domain)
        
    r_uris = ["*"]
    for d in all_domains:
        d = d.strip().lower()
        if d:
            r_uris.append(f"https://{d}/oauth2/callback")
            r_uris.append(f"http://{d}/oauth2/callback")
            r_uris.append(f"https://{d}/*")
            r_uris.append(f"http://{d}/*")
            
    cookie_domains_str, _ = get_all_cookie_and_whitelist_domains(data, extra_domain=extra_domain)
    for rd in cookie_domains_str.split(','):
        rd = rd.strip().lstrip('.')
        if rd:
            r_uris.append(f"https://{rd}/oauth2/callback")
            r_uris.append(f"http://{rd}/oauth2/callback")
            r_uris.append(f"https://{rd}/*")
            r_uris.append(f"http://{rd}/*")
            
    unique_r_uris = list(set(r_uris))
    redirect_uris_json = json.dumps(unique_r_uris)

    # 优先通过 Keycloak Admin REST API 查找并更新/创建客户端
    try:
        clients_res, code, _ = call_keycloak_api("clients", "GET", params={"clientId": GLOBAL_SSO_CLIENT_ID})
        client_payload = {
            "clientId": GLOBAL_SSO_CLIENT_ID,
            "secret": client_secret,
            "enabled": True,
            "publicClient": False,
            "protocol": "openid-connect",
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": False,
            "redirectUris": unique_r_uris,
            "webOrigins": ["+", "*"]
        }
        if passkey_flow_id:
            client_payload["authenticationFlowBindingOverrides"] = {"browser": passkey_flow_id}

        if code == 200 and isinstance(clients_res, list) and clients_res:
            cid = clients_res[0].get("id")
            if cid:
                u_data, u_code, u_err = call_keycloak_api(f"clients/{cid}", "PUT", json_data=client_payload)
                if u_code in (200, 204):
                    scopes_list, _, _ = call_keycloak_api("client-scopes", "GET")
                    if isinstance(scopes_list, list):
                        for sc_name in ("scope-passkey-only", "scope-password-only"):
                            sc_obj = next((s for s in scopes_list if s.get("name") == sc_name), None)
                            if sc_obj:
                                call_keycloak_api(f"clients/{cid}/optional-client-scopes/{sc_obj['id']}", "PUT")
                    log("Keycloak 全局 SSO 自适应客户端已通过 REST API 成功同步更新")
                    return True, "", client_secret
        elif code == 200 and isinstance(clients_res, list) and not clients_res:
            c_data, c_code, c_err = call_keycloak_api("clients", "POST", json_data=client_payload)
            if c_code in (200, 201, 204):
                # 获取新建客户端 ID 并绑定 optional scopes
                new_c_res, _, _ = call_keycloak_api("clients", "GET", params={"clientId": GLOBAL_SSO_CLIENT_ID})
                if isinstance(new_c_res, list) and new_c_res:
                    new_cid = new_c_res[0].get("id")
                    scopes_list, _, _ = call_keycloak_api("client-scopes", "GET")
                    if isinstance(scopes_list, list) and new_cid:
                        for sc_name in ("scope-passkey-only", "scope-password-only"):
                            sc_obj = next((s for s in scopes_list if s.get("name") == sc_name), None)
                            if sc_obj:
                                call_keycloak_api(f"clients/{new_cid}/optional-client-scopes/{sc_obj['id']}", "PUT")
                log("Keycloak 全局 SSO 自适应客户端已通过 REST API 成功创建")
                return True, "", client_secret

    except Exception as e:
        log(f"通过 REST API 同步 Keycloak 客户端异常: {e}")

    # Fallback: 使用 docker exec kcadm.sh 登录并配置
    run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "config", "credentials",
        "--server", "http://localhost:8080",
        "--realm", "master",
        "--user", admin_user,
        "--password", admin_pass
    ])
    
    # 检查 global-sso 客户端是否存在
    uuid_rc, uuid_out, _ = run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "get", "clients",
        "-r", "master",
        "-q", f"clientId={GLOBAL_SSO_CLIENT_ID}",
        "--fields", "id",
        "--format", "csv",
        "--noquotes"
    ])
    uuid = uuid_out.strip().splitlines()[0].strip() if uuid_out.strip() else ""

    if uuid:
        up_args = [
            "docker", "exec", KEYCLOAK_CONTAINER,
            "/opt/keycloak/bin/kcadm.sh", "update", f"clients/{uuid}",
            "-r", "master",
            "-s", f"secret={client_secret}",
            "-s", "enabled=true",
            "-s", "publicClient=false",
            "-s", "protocol=openid-connect",
            "-s", "standardFlowEnabled=true",
            "-s", "directAccessGrantsEnabled=false",
            "-s", f"redirectUris={redirect_uris_json}",
            "-s", "webOrigins=[\"+\",\"*\"]"
        ]
        if passkey_flow_id:
            up_args.extend(["-s", f"authenticationFlowBindingOverrides={{\"browser\":\"{passkey_flow_id}\"}}"])
        run_cmd_args(up_args)
        log("Keycloak 全局 SSO Passkey 客户端已同步更新")
    else:
        create_args = [
            "docker", "exec", KEYCLOAK_CONTAINER,
            "/opt/keycloak/bin/kcadm.sh", "create", "clients",
            "-r", "master",
            "-s", f"clientId={GLOBAL_SSO_CLIENT_ID}",
            "-s", f"secret={client_secret}",
            "-s", "enabled=true",
            "-s", "publicClient=false",
            "-s", "protocol=openid-connect",
            "-s", "standardFlowEnabled=true",
            "-s", "directAccessGrantsEnabled=false",
            "-s", f"redirectUris={redirect_uris_json}",
            "-s", "webOrigins=[\"+\",\"*\"]"
        ]
        if passkey_flow_id:
            create_args.extend(["-s", f"authenticationFlowBindingOverrides={{\"browser\":\"{passkey_flow_id}\"}}"])
        rc_c, _, err_c = run_cmd_args(create_args)
        if rc_c != 0:
            log(f"创建 Keycloak 全局 SSO 客户端异常: {err_c}")
            return False, f"创建 Keycloak 客户端失败: {err_c}", client_secret
        log("Keycloak 全局 SSO Passkey 客户端创建成功")
        
    return True, "", client_secret


def ensure_global_sso_container(extra_domain=None):
    """启动或更新全局单一 oauth2-proxy 容器服务 (监听 127.0.0.1:4180)"""
    ok, err, client_secret = ensure_global_sso_client(extra_domain=extra_domain)
    if not ok:
        log(f"初始化全局 SSO 客户端失败: {err}")
        return False, err
        
    _, _, kc_issuer_base = get_keycloak_admin_credentials()
    
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
        except Exception:
            pass
            
    cookie_secret = cfg.get("global_sso_cookie_secret")
    if cookie_secret:
        cookie_secret = decrypt_val(cookie_secret)
    if not cookie_secret:
        cookie_secret = generate_secret(32)
        cfg["global_sso_cookie_secret"] = encrypt_val(cookie_secret)
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
            
    cookie_domains_str, whitelist_domains_str = get_all_cookie_and_whitelist_domains(extra_domain=extra_domain)
    
    # 漏洞#4 修复：构建精确的白名单域名列表，不使用裸 * 通配，防止 OIDC Open Redirect
    # whitelist_domains_str 已由 get_all_cookie_and_whitelist_domains() 生成精确子域名列表（如 *.example.com,example.com）
    # 确保不包含裸 "*"
    safe_whitelist = ",".join(
        d.strip() for d in whitelist_domains_str.split(',')
        if d.strip() and d.strip() != '*'
    )
    
    log(f"正在配置全局单一 SSO 代理服务 (Cookie域: {cookie_domains_str})...")
    
    run_cmd_args(["docker", "rm", "-f", GLOBAL_SSO_CONTAINER])
    
    run_args = [
        "docker", "run", "-d",
        "--name", GLOBAL_SSO_CONTAINER,
        "--restart", "always",
        "--network", "host",
        "-e", "OAUTH2_PROXY_PROVIDER=oidc",
        "-e", f"OAUTH2_PROXY_OIDC_ISSUER_URL={kc_issuer_base}/realms/master",
        "-e", f"OAUTH2_PROXY_CLIENT_ID={GLOBAL_SSO_CLIENT_ID}",
        "-e", f"OAUTH2_PROXY_CLIENT_SECRET={client_secret}",
        "-e", "OAUTH2_PROXY_COOKIE_NAME=_auth_sso",
        "-e", f"OAUTH2_PROXY_COOKIE_SECRET={cookie_secret}",
        "-e", "OAUTH2_PROXY_COOKIE_SECURE=true",

        "-e", f"OAUTH2_PROXY_COOKIE_DOMAINS={cookie_domains_str}",
        "-e", "OAUTH2_PROXY_COOKIE_SAMESITE=lax",
        "-e", "OAUTH2_PROXY_COOKIE_CSRF_PER_REQUEST=true",
        "-e", "OAUTH2_PROXY_APPROVAL_PROMPT=",
        "-e", f"OAUTH2_PROXY_WHITELIST_DOMAINS={safe_whitelist}",
        "-e", "OAUTH2_PROXY_SKIP_PROVIDER_BUTTON=true",
        "-e", "OAUTH2_PROXY_CODE_CHALLENGE_METHOD=S256",
        "-e", "OAUTH2_PROXY_EMAIL_DOMAINS=*",
        "-e", "OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true",
        "-e", "OAUTH2_PROXY_USER_ID_CLAIM=preferred_username",
        "-e", "OAUTH2_PROXY_SET_XAUTHREQUEST=true",
        "-e", "OAUTH2_PROXY_PASS_ACCESS_TOKEN=true",
        "-e", "OAUTH2_PROXY_PASS_AUTHORIZATION_HEADER=true",
        "-e", "OAUTH2_PROXY_REVERSE_PROXY=true",
        "-e", f"OAUTH2_PROXY_HTTP_ADDRESS=127.0.0.1:{GLOBAL_SSO_PORT}",
        "quay.io/oauth2-proxy/oauth2-proxy:v7.6.0"
    ]

    
    rc, out, err_out = run_cmd_args(run_args)
    if rc != 0:
        # 漏洞#12 修复：日志脱敏，不直接打印可能含有 secret 的 err_out
        safe_err = re.sub(r'(secret|password|key|token)=[^\s,\]]+', r'\1=***', err_out.strip(), flags=re.IGNORECASE)
        log(f"全局 SSO 容器启动失败: {safe_err}")
        return False, "SSO 容器启动失败，请查看系统日志"
        
    log(f"全局单一 SSO 代理服务已成功启动并就绪 (127.0.0.1:{GLOBAL_SSO_PORT})")
    return True, ""


def create_keycloak_client(domain, client_id, client_secret):
    """创建或更新 Keycloak Client (兼容保留)"""
    return ensure_global_sso_client(client_secret)

def delete_keycloak_client(client_id):
    if client_id == GLOBAL_SSO_CLIENT_ID:
        return
    log("删除 Keycloak Client: {}".format(client_id))
    admin_user, admin_pass, _ = get_keycloak_admin_credentials()
    run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "config", "credentials",
        "--server", "http://localhost:8080",
        "--realm", "master",
        "--user", admin_user,
        "--password", admin_pass
    ])
    uuid_rc, uuid_out, _ = run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "get", "clients",
        "-r", "master",
        "-q", f"clientId={client_id}",
        "--fields", "id",
        "--format", "csv",
        "--noquotes"
    ])
    uuid = uuid_out.strip().splitlines()[0].strip() if uuid_out.strip() else ""
    if uuid:
        run_cmd_args([
            "docker", "exec", KEYCLOAK_CONTAINER,
            "/opt/keycloak/bin/kcadm.sh", "delete", f"clients/{uuid}",
            "-r", "master"
        ])

def stop_oauth2_container(container_name):
    if not container_name or container_name == GLOBAL_SSO_CONTAINER:
        return
    log(f"停止并清理历史独立容器: {container_name}")
    run_cmd_args(["docker", "rm", "-f", container_name])

def create_oauth2_container(domain, oauth_port, client_id, client_secret):
    """复用全局单一 SSO 容器"""
    ok, err = ensure_global_sso_container(extra_domain=domain)
    return ok, GLOBAL_SSO_CONTAINER, "", err

def get_proxy_conf_path(domain):
    if not domain:
        return None
    domain = domain.strip().lower()
    base_dirs = [
        f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}",
        f"/opt/1panel/www/sites/{domain}"
    ]
    for b in base_dirs:
        if os.path.exists(b):
            proxy_dir = os.path.join(b, "proxy")
            os.makedirs(proxy_dir, exist_ok=True)
            return os.path.join(proxy_dir, "root.conf")
            
    parent_sites = None
    if os.path.exists("/opt/1panel/apps/openresty/openresty/www/sites"):
        parent_sites = "/opt/1panel/apps/openresty/openresty/www/sites"
    elif os.path.exists("/opt/1panel/www/sites"):
        parent_sites = "/opt/1panel/www/sites"
    elif os.path.exists("/www/sites"):
        parent_sites = "/www/sites"
        
    if parent_sites:
        site_dir = os.path.join(parent_sites, domain)
        proxy_dir = os.path.join(site_dir, "proxy")
        os.makedirs(proxy_dir, exist_ok=True)
        os.makedirs(os.path.join(site_dir, "log"), exist_ok=True)
        os.makedirs(os.path.join(site_dir, "ssl"), exist_ok=True)
        return os.path.join(proxy_dir, "root.conf")
    return None

def reload_openresty():
    """统一安全重载 Nginx / OpenResty 容器"""
    try:
        or_rc, or_out, or_err = run_cmd_args(["docker", "ps", "-q", "-f", "name=openresty"])
        openresty_id = or_out.strip().splitlines()[0].strip() if or_out.strip() else ""
        if openresty_id:
            t_rc, _, t_err = run_cmd_args(["docker", "exec", openresty_id, "nginx", "-t"])
            if t_rc == 0:
                run_cmd_args(["docker", "exec", openresty_id, "nginx", "-s", "reload"])
                log("OpenResty / Nginx 站点配置已成功重载！")
                return True
            else:
                log(f"OpenResty 配置测试失败: {t_err.strip()}")
    except Exception as e:
        log(f"重载 OpenResty 异常: {e}")
    return False

def get_allowed_users_for_domain(domain, users_data=None):
    """
    计算特定域名允许访问的用户列表。
    返回: (is_all_allowed: bool, allowed_usernames: list)
    - 若没有任何用户受到站点限制（所有用户均为 *），返回 (True, ["*"])
    - 若有用户被配置为仅允许访问某些特定站点，则返回 (False, [该站点允许的用户名列表...])
    """
    try:
        admin_user, _, _ = get_keycloak_admin_credentials()
        if users_data is None:
            users_data, code, _ = call_keycloak_api("users", "GET", params={"briefRepresentation": "false"})
            if code != 200 or not isinstance(users_data, list):
                return True, ["*"]

        has_restricted_user = False
        allowed_users = set()
        if admin_user:
            allowed_users.add(admin_user)

        for u in users_data:
            if not u.get("enabled", True):
                continue
            username = u.get("username", "")
            if not username:
                continue

            if username == admin_user:
                allowed_users.add(username)
                continue

            attrs = u.get("attributes", {})
            raw_sites = attrs.get("allowed_sites", ["*"])
            user_sites = []
            if isinstance(raw_sites, str):
                user_sites = [s.strip() for s in raw_sites.split(",") if s.strip()]
            elif isinstance(raw_sites, list):
                for item in raw_sites:
                    if isinstance(item, str):
                        for s in item.split(","):
                            if s.strip():
                                user_sites.append(s.strip())
            else:
                user_sites = ["*"]

            if not user_sites or "*" in user_sites:
                allowed_users.add(username)
            else:
                has_restricted_user = True
                if domain in user_sites:
                    allowed_users.add(username)

        if not has_restricted_user:
            return True, ["*"]

        return False, list(allowed_users)
    except Exception as e:
        log(f"计算域名 {domain} 授权用户异常: {e}")
        return True, ["*"]

def sync_all_sites_permissions(users_data=None):
    """当用户站点权限变动时，平滑更新所有受保护站点的 OpenResty 反代配置并重载"""
    try:
        data = load_data()
        if users_data is None:
            users_data, code, _ = call_keycloak_api("users", "GET", params={"briefRepresentation": "false"})
            if code != 200 or not isinstance(users_data, list):
                users_data = None

        for domain, auth in data.items():
            if isinstance(auth, dict) and auth.get('proxy_enabled', True):
                oauth_port = auth.get('oauth_port', GLOBAL_SSO_PORT)
                target_host = auth.get('target_host', '127.0.0.1')
                target_port = auth.get('target_port', 80)
                auth_enabled = auth.get('auth_enabled', True)
                proxy_enabled = auth.get('proxy_enabled', True)
                update_nginx_config(domain, oauth_port, target_host, target_port, auth_enabled, proxy_enabled, reload_nginx=False, users_data=users_data)
        reload_openresty()
        log("所有站点的用户站点访问权限已同步并重载 OpenResty！")
        return True
    except Exception as e:
        log(f"同步所有站点权限异常: {e}")
        return False

def update_nginx_config(domain, oauth_port, target_host, target_port, auth_enabled, proxy_enabled, reload_nginx=True, users_data=None):
    proxy_conf = get_proxy_conf_path(domain)
    if not proxy_conf:
        log("未找到 OpenResty 站点目录，无法生成反代配置文件")
        return None
    
    target_host = target_host.strip() if target_host else "127.0.0.1"
    target_upstream = f"{target_host}:{target_port}"
    sso_port = oauth_port or GLOBAL_SSO_PORT
        
    if not proxy_enabled:
        # 如果反代被关闭，返回 503 状态码
        new_content = """# 反向代理已关闭
location / {
    return 503;
}
"""
    elif not auth_enabled:
        # 普通反向代理（未开启 Keycloak 认证）
        new_content = """# 普通反代（未开启 Keycloak 认证）
location ^~ / {
    proxy_pass http://""" + target_upstream + """;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}
"""
    else:
        is_all_allowed, allowed_users = get_allowed_users_for_domain(domain, users_data=users_data)
        admin_user, admin_pass, kc_public_url = get_keycloak_admin_credentials()

        access_check_lua = ""
        if not is_all_allowed and allowed_users:
            lua_entries = ", ".join([f'["{u}"] = true' for u in allowed_users])
            access_check_lua = f"""
    # 细粒度用户站点访问权限校验 (Access Control)
    access_by_lua_block {{
        local u = ngx.var.preferred_username or ""
        if u == "" then
            u = ngx.var.upstream_http_x_auth_request_preferred_username or ""
        end
        if u == "" then
            u = ngx.var.user or ""
        end
        local allowed = {{ {lua_entries} }}
        if not allowed["*"] and not allowed[u] then
            ngx.status = 403
            ngx.header.content_type = "text/html; charset=utf-8"
            local host = ngx.var.host or ""
            local post_redir = "https://" .. host .. "/"
            local kc_logout_target = "{kc_public_url}/realms/master/protocol/openid-connect/logout?client_id=global-sso&post_logout_redirect_uri=" .. ngx.escape_uri(post_redir)
            local sign_out_url = "/oauth2/sign_out?rd=" .. ngx.escape_uri(kc_logout_target)
            ngx.say([[<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>403 访问受限</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f172a;color:#f8fafc;font-family:system-ui,-apple-system,sans-serif}}.card{{background:#1e293b;padding:36px 32px;border-radius:20px;box-shadow:0 20px 40px rgba(0,0,0,0.5);text-align:center;max-width:440px;border:1px solid rgba(255,255,255,0.08)}}.icon{{font-size:48px;margin-bottom:16px}}h1{{font-size:22px;margin:0 0 10px;font-weight:700;color:#f43f5e}}p{{color:#94a3b8;font-size:14px;line-height:1.6;margin:0 0 24px}}.badge{{display:inline-block;padding:4px 10px;background:rgba(244,63,94,0.15);color:#fb7185;border-radius:6px;font-family:monospace;font-size:13px;margin-bottom:16px}}.btn{{display:inline-block;padding:10px 22px;background:#3b82f6;color:#fff;text-decoration:none;border-radius:10px;font-size:14px;font-weight:600;transition:all .2s;cursor:pointer}}.btn:hover{{background:#2563eb;transform:translateY(-1px)}}</style></head>
<body><div class="card"><div class="icon">🚫</div><div class="badge">账号: ]] .. (u ~= "" and u or "未识别") .. [[</div><h1>403 访问受限</h1><p>您已通过身份认证，但未获得访问当前站点 <strong>]] .. (ngx.var.host or "") .. [[</strong> 的权限。<br>如需开通，请联系管理员分配站点访问权限。</p><a href="]] .. sign_out_url .. [[" class="btn" onclick="this.innerHTML='⏳ 正在注销并跳转登录...'; this.style.pointerEvents='none';">🔄 切换账号登录</a></div></body></html>]])
            ngx.exit(403)
        end
    }}
"""

        all_data_for_site = load_data()
        site_info = all_data_for_site.get(domain, {}) if isinstance(all_data_for_site, dict) else {}
        allow_passkey = site_info.get('allow_passkey', True)
        allow_password = site_info.get('allow_password', True)

        # 完整全局 SSO 认证反代（漏洞#3/#7/#8 全部修复 + 用户站点访问权限校验）
        new_content = """# OAuth2 全局 SSO 认证路径 - 需要大缓冲区处理 cookie
location ^~ /oauth2/ {
    proxy_pass http://127.0.0.1:""" + str(sso_port) + """;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Uri $request_uri;
    
    # 增加缓冲区大小，解决 oauth2 callback header 太大问题
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
}



location = /oauth2/auth {
    internal;
    proxy_pass http://127.0.0.1:""" + str(sso_port) + """/oauth2/auth;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Uri $request_uri;
}

# 漏洞#8 修复: 使用 $uri 替代 $request_uri，防止 HTTP Response Splitting
location @login {
    return 302 https://$host/oauth2/sign_in?rd=$uri$is_args$args;
}

# 漏洞#7 修复: auth_request 子请求 5xx 时返回 503，防止认证服务崩溃时请求穿透到后端
location @auth_error {
    return 503 "Authentication service unavailable";
}

# 主内容 - 需要 SSO 认证 (支持全站 Passkey 免密)
location ^~ / {
    auth_request /oauth2/auth;
    error_page 401 = @login;
    # 漏洞#7 修复: 5xx 错误（如 oauth2-proxy 崩溃时的 502）明确拦截，禁止穿透
    error_page 500 502 503 504 = @auth_error;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    
    # 漏洞#3 修复: 先将所有客户端可能伪造的身份请求头清空，再从 auth_request 结果注入
    proxy_set_header X-User "";
    proxy_set_header X-Email "";
    proxy_set_header X-Auth-Request-User "";
    proxy_set_header X-Auth-Request-Email "";
    proxy_set_header X-Auth-Request-Preferred-Username "";

    auth_request_set $user $upstream_http_x_auth_request_user;
    auth_request_set $email $upstream_http_x_auth_request_email;
    auth_request_set $preferred_username $upstream_http_x_auth_request_preferred_username;
""" + access_check_lua + """
    proxy_pass http://""" + target_upstream + """;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    proxy_set_header X-User $user;
    proxy_set_header X-Email $email;
    proxy_set_header X-Auth-Request-User $user;
    proxy_set_header X-Auth-Request-Email $email;
    proxy_set_header X-Auth-Request-Preferred-Username $preferred_username;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}
"""

    try:
        with open(proxy_conf, 'w') as f:
            f.write(new_content)
        
        if reload_nginx:
            reload_openresty()
        return new_content
    except Exception as e:
        log(f"写入 OpenResty 反代配置失败: {e}")
        return None

        log(f"更新 Nginx 配置文件失败: {str(e)}")
        return None

def ensure_openresty_site_conf(domain):
    if not domain:
        return
    domain = domain.strip().lower()
    conf_dirs = [
        "/opt/1panel/apps/openresty/openresty/conf/conf.d",
        "/opt/1panel/conf/conf.d",
        "/etc/nginx/conf.d"
    ]
    for cd in conf_dirs:
        if os.path.exists(cd):
            conf_file = os.path.join(cd, f"{domain}.conf")
            if not os.path.exists(conf_file):
                # 检查该域名是否已经存在证书文件
                ssl_cert = f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}/ssl/fullchain.pem"
                ssl_key = f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}/ssl/privkey.pem"
                has_ssl = os.path.exists(ssl_cert) and os.path.exists(ssl_key) and os.path.getsize(ssl_cert) > 0
                
                if has_ssl:
                    main_conf = """server {
    listen 80;
    server_name """ + domain + """;
    
    location ^~ /.well-known/acme-challenge {
        default_type "text/plain";
        root /usr/share/nginx/html;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name """ + domain + """;
    
    access_log /www/sites/""" + domain + """/log/access.log main;
    error_log /www/sites/""" + domain + """/log/error.log;
    
    ssl_certificate /www/sites/""" + domain + """/ssl/fullchain.pem;
    ssl_certificate_key /www/sites/""" + domain + """/ssl/privkey.pem;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    add_header Strict-Transport-Security "max-age=31536000";
    
    include /www/sites/""" + domain + """/proxy/*.conf;
}
"""
                else:
                    main_conf = """server {
    listen 80;
    server_name """ + domain + """;
    
    access_log /www/sites/""" + domain + """/log/access.log main;
    error_log /www/sites/""" + domain + """/log/error.log;
    
    location ^~ /.well-known/acme-challenge {
        default_type "text/plain";
        root /usr/share/nginx/html;
    }
    
    include /www/sites/""" + domain + """/proxy/*.conf;
}
"""
                try:
                    with open(conf_file, 'w', encoding='utf-8') as f:
                        f.write(main_conf)
                    log(f"已自动生成 OpenResty 站点主配置文件: {conf_file}")
                except Exception as e:
                    log(f"生成主配置文件异常: {e}")

def create_nginx_auth(domain, oauth_port, target_host, target_port):
    log("配置 Nginx / OpenResty 站点与反代...")
    target_host = target_host.strip() if target_host else "127.0.0.1"
    target_upstream = f"{target_host}:{target_port}"
    
    # 1. 尝试通过 1Panel API 自动建站（若已配置 API Key）
    if ONEPANEL_API_KEY:
        api_payload = {
            "primaryDomain": domain,
            "type": "proxy",
            "alias": domain,
            "webSiteGroupId": 1,
            "domains": [{"domain": domain, "port": 80}],
            "appType": "installed",
            "appInstallId": 1,
            "proxy": f"http://{target_upstream}",
            "remark": "Auth Manager 自动创建"
        }
        res = call_1panel_api("/api/v1/websites", "POST", api_payload)
        if res and res.get("code") == 200:
            log("通过 1Panel API 成功创建反向代理网站")
            time.sleep(1.5)
        else:
            if res:
                log(f"1Panel API 建站提示: {res.get('message', res)}")
    
    # 2. 无论是否调用 API，均确保站点主配置文件与目录存在（自愈机制）
    ensure_openresty_site_conf(domain)
    
    # 3. 获取 proxy 配置文件路径
    proxy_conf = get_proxy_conf_path(domain)
    if not proxy_conf:
        log("未找到 OpenResty 站点目录，请确认 OpenResty 已安装")
        return None
    
    # 4. 写入完整认证反代配置并重载
    new_conf = update_nginx_config(domain, oauth_port, target_host, target_port, auth_enabled=True, proxy_enabled=True)
    return new_conf

def toggle_nginx_ssl(domain, enable):
    # 查找 1Panel 中的网站ID，修复：1Panel 该接口 orderBy 和 order 为必填字段，须在此补全
    ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
    if not (ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]):
        log("警告: 未在 1Panel 中找到对应的网站ID，跳过 SSL 设置")
        return False
        
    ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
    if not ws_item:
        log("未匹配到对应的网站信息")
        return False
        
    ws_id = ws_item["id"]
    ssl_id = 0
    
    if enable:
        # 获取全部证书列表并在 Python 中进行手动精确过滤，解决 1Panel 接口不支持 domain 精确搜索的问题
        ssl_res = call_1panel_api("/api/v1/websites/ssl/search", "POST", {"page": 1, "pageSize": 100, "orderBy": "created_at", "order": "null"})
        if ssl_res and ssl_res.get("code") == 200 and ssl_res.get("data") and ssl_res["data"]["items"]:
            items = ssl_res["data"]["items"]
            # 匹配对应域名且状态已就绪的证书
            matched_ssl = next((x for x in items if x.get("primaryDomain") == domain and x.get("status", "").lower() in ["ready", "success", "issued"]), None)
            if matched_ssl:
                ssl_id = matched_ssl["id"]
            else:
                log(f"警告: 未查找到状态为 ready 且匹配域名 {domain} 的已签发证书。")
                return False
        else:
            log("警告: 1Panel 证书列表查询失败")
            return False
            
    https_payload = {
        "websiteID": ws_id,
        "enable": enable,
        "websiteSSLID": ssl_id,
        "type": "existed" if ssl_id else "manual",
        "httpConfig": "HTTPToHTTPS" if enable else "HTTPAlso",
        "httpsPorts": [443]
    }
    res = call_1panel_api(f"/api/v1/websites/{ws_id}/https", "POST", https_payload)
    if res and res.get("code") == 200:
        log(f"1Panel SSL 设置成功（状态: {enable}）")
        return True
    log(f"1Panel SSL 设置失败: {res}")
    return False

def delete_1panel_website(domain):
    ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
    if not (ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]):
        log(f"未在 1Panel 中找到域名 {domain}，无需删除。")
        return False
        
    ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
    if not ws_item:
        log(f"未匹配到对应的 1Panel 网站信息，跳过删除。")
        return False
        
    ws_id = ws_item["id"]
    log(f"准备删除 1Panel 网站 (ID: {ws_id})")
    
    del_res = call_1panel_api("/api/v1/websites/del", "POST", {"id": ws_id, "forceDelete": True})
    if del_res and del_res.get("code") == 200:
        log("1Panel 网站删除成功")
        return True
        
    log(f"1Panel 网站删除失败: {del_res}")
    return False

def do_apply_ssl(domain, acme_id, dns_id=None):
    if not domain:
        return False, "域名参数缺失"
        
    # 若未指定 acme_id，自动从 1Panel 查询默认 ACME 账户
    if not acme_id:
        acme_res = call_1panel_api("/api/v1/websites/acme/search", "POST", {"page": 1, "pageSize": 10, "orderBy": "created_at", "order": "null"})
        if acme_res and acme_res.get("code") == 200 and acme_res.get("data") and acme_res["data"].get("items"):
            acme_id = acme_res["data"]["items"][0]["id"]
            
    if not acme_id:
        return False, "未在 1Panel 中找到可用的 ACME 账户 (请先在 1Panel -> 证书 中添加 ACME 账户)"

    log(f"开始为 {domain} 申请 SSL 证书...")
    ssl_payload = {
        "primaryDomain": domain,
        "provider": "dnsAccount" if dns_id else "http",
        "acmeAccountId": int(acme_id),
        "autoRenew": True,
        "description": "Auto SSL by KAM",
        "apply": True,
        "keyType": "2048",
    }
    if dns_id:
        ssl_payload["dnsAccountId"] = int(dns_id)
    
    log("正在向 1Panel 提交 SSL 申请...")
    ssl_res = call_1panel_api("/api/v1/websites/ssl", "POST", ssl_payload)
    if not (ssl_res and ssl_res.get("code") == 200 and ssl_res.get("data")):
        err_msg = ssl_res.get('message', '未知错误') if ssl_res else '1Panel 无响应'
        log(f"提交 SSL 申请失败: {err_msg}")
        return False, f"提交 SSL 申请失败: {err_msg}"
        
    ssl_id = ssl_res["data"]["id"]
    log(f"申请已提交 (SSL ID: {ssl_id})，等待证书签发中 (通常需要 15-60 秒)...")
    
    ssl_ready = False
    last_log_size = 0
    log_file = None
    
    def read_1panel_log(current_last_size, current_log_file):
        try:
            import glob
            if not current_log_file:
                possible_logs = glob.glob(f"/opt/1panel/log/ssl/*{domain}-ssl-{ssl_id}.log")
                if not possible_logs:
                    possible_logs = glob.glob(f"/opt/1panel/log/ssl/{domain}-ssl-{ssl_id}.log")
                if possible_logs:
                    current_log_file = possible_logs[0]
            
            if current_log_file and os.path.exists(current_log_file):
                with open(current_log_file, 'r', encoding='utf-8') as f:
                    f.seek(current_last_size)
                    new_content = f.read()
                    if new_content:
                        for line in new_content.strip().split('\n'):
                            if line:
                                log(f"[1Panel SSL] {line}")
                    current_last_size = f.tell()
        except Exception as e:
            log(f"[Debug] 读取日志异常: {str(e)}")
        return current_last_size, current_log_file
    
    for _ in range(36): # 最多轮询等待 3 分钟
        time.sleep(5)
        last_log_size, log_file = read_1panel_log(last_log_size, log_file)
        
        search_res = call_1panel_api("/api/v1/websites/ssl/search", "POST", {"page": 1, "pageSize": 100, "orderBy": "created_at", "order": "null"})
        if search_res and search_res.get("code") == 200 and search_res.get("data") and search_res["data"]["items"]:
            item = next((x for x in search_res["data"]["items"] if x["id"] == ssl_id), None)
            if item:
                status = item.get("status", "")
                if status in ["Ready", "Success", "Issued", "ready", "success", "issued"]:
                    ssl_ready = True
                    last_log_size, log_file = read_1panel_log(last_log_size, log_file)
                    log("证书签发成功！")
                    break
                elif "Error" in status or "Failed" in status or "error" in status.lower() or "fail" in status.lower():
                    err_msg = item.get('message', status)
                    last_log_size, log_file = read_1panel_log(last_log_size, log_file)
                    log(f"证书申请失败: {err_msg}")
                    return False, f"1Panel API返回失败状态: {err_msg}"
                    
    if not ssl_ready:
        log("证书申请超时 (超过3分钟)，请前往 1Panel 后台查看详情")
        return False, "证书申请超过3分钟超时，请前往 1Panel 后台查看详情"
        
    log("正在将证书绑定到网站并开启 HTTPS...")
    ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
    if ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]:
        ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
        if ws_item:
            ws_id = ws_item["id"]
            https_payload = {
                "websiteID": ws_id,
                "enable": True,
                "websiteSSLID": ssl_id,
                "type": "existed",
                "httpConfig": "HTTPToHTTPS",
                "httpsPorts": [443]
            }
            call_1panel_api(f"/api/v1/websites/{ws_id}/https", "POST", https_payload)
            log("HTTPS 绑定成功，网站配置已重载！")
            
            fresh_data = load_data()
            if domain in fresh_data:
                fresh_data[domain]['ssl_enabled'] = True
                save_data(fresh_data)
            return True, ""
            
    log("绑定失败：未能找到 1Panel 反代网站信息")
    return False, "未找到对应的反代网站信息"

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        web_port = int(request.form.get('web_port', 8088))
        keycloak_url = request.form.get('keycloak_url', '').strip()
        if keycloak_url:
            if not keycloak_url.startswith("http://") and not keycloak_url.startswith("https://"):
                keycloak_url = "https://" + keycloak_url
            keycloak_url = keycloak_url.rstrip("/")
        keycloak_admin = request.form.get('keycloak_admin', '').strip()
        keycloak_password = request.form.get('keycloak_password', '').strip()
        keycloak_container = request.form.get('keycloak_container', '').strip()
        onepanel_port = int(request.form.get('onepanel_port', 40455))
        onepanel_api_key = request.form.get('onepanel_api_key', '').strip()
        
        cloudflare_api_token = request.form.get('cloudflare_api_token', '').strip()
        cloudflare_server_ip = request.form.get('cloudflare_server_ip', '').strip()
        cloudflare_proxied = request.form.get('cloudflare_proxied', 'false').lower() in ['true', '1', 'on']
        
        console_username = request.form.get('console_username', '').strip()
        console_password = request.form.get('console_password', '').strip()
        
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
            except Exception:
                pass
                
        cfg['web_port'] = web_port
        cfg['keycloak_url'] = keycloak_url
        cfg['keycloak_admin'] = keycloak_admin
        cfg['keycloak_container'] = keycloak_container
        cfg['onepanel_port'] = onepanel_port
        cfg['cloudflare_server_ip'] = cloudflare_server_ip
        cfg['cloudflare_proxied'] = cloudflare_proxied
        
        if console_username:
            cfg['console_username'] = console_username
        if console_password:
            cfg['console_password'] = encrypt_val(console_password)
        if keycloak_password:
            cfg['keycloak_password'] = encrypt_val(keycloak_password)
        if onepanel_api_key:
            cfg['onepanel_api_key'] = encrypt_val(onepanel_api_key)
        if cloudflare_api_token:
            cfg['cloudflare_api_token'] = encrypt_val(cloudflare_api_token)
            
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            flash(f'保存失败: {str(e)}', 'danger')
            return redirect('/settings')
            
        load_config()
        flash('配置已成功保存！如果您修改了“面板监听端口 (web_port)”，需手动在服务器终端执行 "sudo systemctl restart keycloak-auth-manager.service" 才能生效。', 'success')
        return redirect('/settings')
        
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass
    return render_template('settings.html', config=cfg)

@app.route('/api/settings', methods=['POST'])
def api_settings():
    try:
        web_port = int(request.form.get('web_port', 8088))
        keycloak_url = request.form.get('keycloak_url', '').strip()
        if keycloak_url:
            if not keycloak_url.startswith("http://") and not keycloak_url.startswith("https://"):
                keycloak_url = "https://" + keycloak_url
            keycloak_url = keycloak_url.rstrip("/")
        keycloak_admin = request.form.get('keycloak_admin', '').strip()
        keycloak_password = request.form.get('keycloak_password', '').strip()
        keycloak_container = request.form.get('keycloak_container', '').strip()
        onepanel_port = int(request.form.get('onepanel_port', 40455))
        onepanel_api_key = request.form.get('onepanel_api_key', '').strip()
        
        cloudflare_api_token = request.form.get('cloudflare_api_token', '').strip()
        cloudflare_server_ip = request.form.get('cloudflare_server_ip', '').strip()
        cloudflare_proxied = request.form.get('cloudflare_proxied', 'false').lower() in ['true', '1', 'on']
        
        console_username = request.form.get('console_username', '').strip()
        console_password = request.form.get('console_password', '').strip()

        cfg = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
            except Exception:
                pass
                
        cfg['web_port'] = web_port
        cfg['keycloak_url'] = keycloak_url
        cfg['keycloak_admin'] = keycloak_admin
        cfg['keycloak_container'] = keycloak_container
        cfg['onepanel_port'] = onepanel_port
        cfg['cloudflare_server_ip'] = cloudflare_server_ip
        cfg['cloudflare_proxied'] = cloudflare_proxied
        
        if console_username:
            cfg['console_username'] = console_username
        if console_password:
            cfg['console_password'] = encrypt_val(console_password)
        if keycloak_password:
            cfg['keycloak_password'] = encrypt_val(keycloak_password)
        if onepanel_api_key:
            cfg['onepanel_api_key'] = encrypt_val(onepanel_api_key)
        if cloudflare_api_token:
            cfg['cloudflare_api_token'] = encrypt_val(cloudflare_api_token)
            
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
            
        load_config()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def migrate_to_single_sso():
    """将所有存量站点平滑迁移收敛至单个全局 SSO 代理服务 (127.0.0.1:4180) 并清理旧容器"""
    log("=== 开始执行多容器向全局单一 SSO 架构平滑迁移 ===")
    
    # 1. 确保全局单一 SSO 容器就绪
    ok, err = ensure_global_sso_container()
    if not ok:
        log(f"初始化全局 SSO 服务失败: {err}")
        return False, err
        
    data = load_data()
    
    # 2. 清理所有旧的 oauth2-<domain> 单域名容器
    for domain, auth in data.items():
        if not isinstance(auth, dict):
            continue
        old_container = auth.get("container_name")
        if old_container and old_container != GLOBAL_SSO_CONTAINER:
            stop_oauth2_container(old_container)
            
    # 清理所有遗留的历史单站点 oauth2 容器
    rc_ps, out_ps, _ = run_cmd_args(["docker", "ps", "-a", "--filter", "name=oauth2-", "--format", "{{.Names}}"])
    if rc_ps == 0 and out_ps:
        for cname in out_ps.splitlines():
            cname = cname.strip()
            if cname and cname != GLOBAL_SSO_CONTAINER:
                stop_oauth2_container(cname)
                
    # 3. 重新生成全部站点的 Nginx 反代配置文件（统一指向 127.0.0.1:4180）
    results = []
    for domain, auth in data.items():
        if not isinstance(auth, dict):
            continue
        target_host = auth.get("target_host", "127.0.0.1")
        target_port = auth.get("target_port", auth.get("port", 80))
        auth_enabled = auth.get("auth_enabled", True)
        proxy_enabled = auth.get("proxy_enabled", True)
        
        auth["oauth_port"] = GLOBAL_SSO_PORT
        auth["container_name"] = GLOBAL_SSO_CONTAINER
        auth["client_id"] = GLOBAL_SSO_CLIENT_ID
        
        new_conf = update_nginx_config(domain, GLOBAL_SSO_PORT, target_host, target_port, auth_enabled, proxy_enabled, reload_nginx=False)
        if new_conf:
            auth["nginx_config"] = new_conf
            results.append({"domain": domain, "status": "success"})
        else:
            results.append({"domain": domain, "status": "failed", "error": "生成 Nginx 配置失败"})
            
    save_data(data)
    
    # 4. 统一测试并重载 OpenResty
    reload_openresty()
    log(f"=== 全局单一 SSO 架构迁移完成！{len(results)} 个站点已统一接入全局 SSO 代理进程 ===")
    return True, results

def redeploy_all_security():
    """兼容旧接口调用"""
    ok, res = migrate_to_single_sso()
    return res if isinstance(res, list) else [{"domain": "global-sso", "status": "success" if ok else "failed"}]

@app.route('/api/security/redeploy_all', methods=['POST'])
def api_security_redeploy_all():
    try:
        ok, results = migrate_to_single_sso()
        return json.dumps({"success": ok, "results": results})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@app.route('/api/cloudflare/zones')
def api_cloudflare_zones():
    zones = get_cloudflare_zones()
    server_ip = get_server_public_ip()
    return json.dumps({
        "configured": bool(CLOUDFLARE_API_TOKEN),
        "zones": zones,
        "server_ip": server_ip,
        "default_proxied": CLOUDFLARE_PROXIED
    })

@app.route('/favicon.ico')
@app.route('/favicon.svg')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')

@app.route('/')
def index():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        except Exception:
            pass
    return render_template('index.html', auths=load_data(), config=cfg)

@app.route('/add')
def add_page():
    return render_template('add.html')

@app.route('/api/logs')
def api_logs():
    last_id_param = request.args.get('last_id')
    header_last_id = request.headers.get('Last-Event-ID')
    try:
        client_last_id = int(last_id_param if last_id_param is not None else (header_last_id or 0))
    except (ValueError, TypeError):
        client_last_id = 0

    def gen(start_id):
        cur_id = start_id
        try:
            while True:
                new_entries = []
                with logs_lock:
                    for item in log_history:
                        if item['id'] > cur_id:
                            new_entries.append(item)
                for entry in new_entries:
                    cur_id = entry['id']
                    yield f"id: {entry['id']}\ndata: {entry['text']}\n\n"
                # 心跳包保证连接不被反代关闭，同时规避缓存
                yield ": heartbeat\n\n"
                time.sleep(0.5)
        except GeneratorExit:
            pass

    res = Response(stream_with_context(gen(client_last_id)), mimetype='text/event-stream')
    res.headers['Cache-Control'] = 'no-cache, no-transform'
    res.headers['X-Accel-Buffering'] = 'no'
    res.headers['Connection'] = 'keep-alive'
    res.headers['Content-Type'] = 'text/event-stream'
    return res

@app.route('/api/logs/poll')
def api_logs_poll():
    last_id_param = request.args.get('last_id', '0')
    try:
        client_last_id = int(last_id_param)
    except (ValueError, TypeError):
        client_last_id = 0
    new_entries = []
    max_id = client_last_id
    with logs_lock:
        for item in log_history:
            if item['id'] > client_last_id:
                new_entries.append(item)
                if item['id'] > max_id:
                    max_id = item['id']
    return json.dumps({"logs": new_entries, "last_id": max_id})

@app.route('/api/acme_accounts')
def api_acme_accounts():
    res = call_1panel_api("/api/v1/websites/acme/search", "POST", {"page": 1, "pageSize": 100, "orderBy": "created_at", "order": "null"})
    if not res or res.get("code") != 200:
        res = call_1panel_api("/api/v1/websites/ca/search", "POST", {"page": 1, "pageSize": 100, "orderBy": "created_at", "order": "null"})
    accounts = []
    if res and res.get("code") == 200 and res.get("data") and res["data"].get("items"):
        for item in res["data"]["items"]:
            email = item.get("email") or item.get("acmeAccount", {}).get("email") or f"ACME #{item.get('id')}"
            acc_type = f" ({item.get('type')})" if item.get('type') else ""
            accounts.append({"id": item["id"], "email": f"{email}{acc_type}"})
    return json.dumps(accounts)

@app.route('/api/dns_accounts')
def api_dns_accounts():
    res = call_1panel_api("/api/v1/websites/dns/search", "POST", {"page":1, "pageSize":100, "orderBy":"created_at", "order":"null"})
    accounts = []
    if res and res.get("code") == 200 and res.get("data") and res["data"].get("items"):
        for item in res["data"]["items"]:
            accounts.append({"id": item["id"], "name": item["name"]})
    return json.dumps(accounts)

@app.route('/api/create', methods=['POST'])
def api_create():
    clear_logs()
    domain = request.form.get('domain', '').strip().lower()
    port = request.form.get('port', '').strip()
    target_type = request.form.get('target_type', 'local').strip()
    target_host = request.form.get('target_host', '').strip()
    
    if target_type == 'custom':
        if not target_host:
            return json.dumps({"success": False, "error": "自定义模式下目标主机/IP必填"})
        # 清理用户误输入的 http:// 或 https://
        target_host = re.sub(r'^https?://', '', target_host).rstrip('/')
    else:
        target_host = '127.0.0.1'
    
    if not domain or not port:
        return json.dumps({"success": False, "error": "域名和端口必填"})
    # 漏洞#11 修复：严格校验 domain 格式，防止路径遍历 → 任意文件写入 RCE
    if not is_valid_domain(domain):
        return json.dumps({"success": False, "error": "域名格式非法，仅允许合法的 DNS 域名（小写字母、数字、连字符和点）"})
    try:
        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError("端口范围非法")
    except Exception:
        return json.dumps({"success": False, "error": "端口必须是 1-65535 的数字"})
    
    data = load_data()
    if domain in data:
        return json.dumps({"success": False, "error": "该域名已配置"})

    
    # 1. 优先执行 Cloudflare DNS 记录添加 (若启用)
    cf_add_dns = request.form.get('cf_add_dns', 'false').lower() in ['true', '1', 'on']
    if cf_add_dns:
        if not CLOUDFLARE_API_TOKEN:
            return json.dumps({"success": False, "error": "未在设置中配置 Cloudflare API Token，无法自动添加 DNS"})
        cf_proxied_form = request.form.get('cf_proxied')
        cf_proxied_val = cf_proxied_form.lower() in ['true', '1', 'on'] if cf_proxied_form is not None else None
        cf_server_ip = request.form.get('cf_server_ip', '').strip()
        
        log("----------------------------------------")
        log(f"开始通过 Cloudflare API 解析域名 {domain}...")
        dns_ok, dns_err = add_or_update_cloudflare_dns(domain, server_ip=cf_server_ip, proxied=cf_proxied_val)
        if not dns_ok:
            log(f"❌ Cloudflare DNS 配置失败: {dns_err}")
            return json.dumps({"success": False, "error": f"Cloudflare DNS 解析失败: {dns_err}"})
        log("✅ Cloudflare DNS 记录已就绪！")
        log("----------------------------------------")
    
    log(f"开始配置 {domain} (目标地址: {target_host}:{port})...")
    
    # 2. 确保全局单一 SSO 代理容器与通配 Passkey 客户端就绪（无需为新域名单独创建容器）
    ok, err = ensure_global_sso_container(extra_domain=domain)
    if not ok:
        return json.dumps({"success": False, "error": f"全局 SSO 认证服务就绪失败: {err}"})
    
    allow_passkey = request.form.get('allow_passkey', 'true').lower() in ['true', '1', 'on']
    allow_password = request.form.get('allow_password', 'true').lower() in ['true', '1', 'on']
    if not allow_passkey and not allow_password:
        return json.dumps({"success": False, "error": "必须至少启用一种登录认证方式（Passkey 或密码）"})

    fresh_data = load_data()
    fresh_data[domain] = {
        'client_id': GLOBAL_SSO_CLIENT_ID, 
        'oauth_port': GLOBAL_SSO_PORT,
        'target_host': target_host,
        'target_port': port,
        'container_name': GLOBAL_SSO_CONTAINER, 
        'created_at': datetime.now().isoformat(),
        'proxy_enabled': True,
        'ssl_enabled': check_domain_ssl_enabled(domain),
        'auth_enabled': True,
        'allow_passkey': allow_passkey,
        'allow_password': allow_password
    }
    save_data(fresh_data)

    # 3. 极速生成 Nginx / OpenResty 反代配置（统一接入 127.0.0.1:4180）
    conf = create_nginx_auth(domain, GLOBAL_SSO_PORT, target_host, port)
    if conf:
        fresh_data[domain]['nginx_config'] = conf
        save_data(fresh_data)
    else:
        log("Nginx 配置失败，请手动检查")

    
    # 检查是否勾选了同时申请 SSL 证书
    apply_ssl = request.form.get('apply_ssl', 'false').lower() in ['true', '1', 'on']
    if apply_ssl:
        acme_id = request.form.get('acme_id')
        dns_id = request.form.get('dns_id')
        log("----------------------------------------")
        log(f"检测到勾选申请证书，正在为 {domain} 申请 SSL 证书...")
        ssl_ok, ssl_err = do_apply_ssl(domain, acme_id, dns_id)
        if ssl_ok:
            log("🎉 认证配置与 SSL 证书申请已全部成功就绪！")
        else:
            log(f"⚠️ 认证配置已完成，但 SSL 申请未完成: {ssl_err}")
            log("您可以在后续前往“证书申请”页面重新提交申请。")
    else:
        log("🎉 认证配置完成! (已接入全局 SSO 与 Passkey 免密支持)")
        
    return json.dumps({"success": True, "ssl_applied": apply_ssl})

@app.route('/api/apply_ssl', methods=['POST'])
def api_apply_ssl():
    clear_logs()
    domain = request.form.get('domain', '').strip().lower()
    acme_id = request.form.get('acme_id')
    dns_id = request.form.get('dns_id')
    
    ssl_ok, ssl_err = do_apply_ssl(domain, acme_id, dns_id)
    if ssl_ok:
        log("全部完成!")
        return json.dumps({"success": True})
    else:
        return json.dumps({"success": False, "error": ssl_err})

@app.route('/detail/<domain>')
def detail(domain):
    domain = domain.strip().lower()
    data = load_data()
    if domain not in data:
        return redirect(url_for('index'))
    auth = data[domain]
    
    # 实时从 1Panel 查询此站点的 HTTPS 开启状态
    ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
    if ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]:
        ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
        if ws_item:
            real_ssl_state = ws_item.get("protocol", "").upper() == "HTTPS"
            if auth.get('ssl_enabled') != real_ssl_state:
                auth['ssl_enabled'] = real_ssl_state
                save_data(data)
                
    rc, out, err = run_cmd_args([
        "docker", "ps", 
        "--filter", f"name={GLOBAL_SSO_CONTAINER}", 
        "--format", "{{.Status}}"
    ])
    auth['status'] = out.strip() or "全局 SSO 运行中"
    return render_template('detail.html', domain=domain, auth=auth)

def async_cleanup_domain_resources(client_id, container_name, domain):
    """在后台线程中异步彻底清理 1Panel 站点与 Nginx 配置，避免阻塞 Web 响应导致超时"""
    # 仅清理非全局容器
    if container_name and container_name != GLOBAL_SSO_CONTAINER:
        try:
            stop_oauth2_container(container_name)
        except Exception as e:
            log(f"[后台释放] 删除容器 {container_name} 异常: {e}")
            
    # 仅清理非全局 client
    if client_id and client_id != GLOBAL_SSO_CLIENT_ID:
        try:
            delete_keycloak_client(client_id)
        except Exception as e:
            log(f"[后台释放] 删除 Keycloak Client {client_id} 异常: {e}")
            
    if domain:
        try:
            delete_1panel_website(domain)
        except Exception as e:
            log(f"[后台释放] 删除 1Panel 网站 {domain} 异常: {e}")
            
    log(f"[后台释放] 域名 {domain} 的底层关联资源已全部销毁清理完成")

@app.route('/delete/<domain>', methods=['POST'])
def delete(domain):
    domain = domain.strip().lower()
    log(f"收到删除请求，domain: '{domain}'")
    data = load_data()
    
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        request.is_json
    )
    
    if domain not in data: 
        log(f"域名 {domain} 不在数据中，直接返回成功")
        if is_ajax:
            return jsonify({"success": True, "msg": f"域名 {domain} 已被移除"})
        return redirect(url_for('index'))
        
    auth = data[domain]
    client_id = auth.get('client_id')
    container_name = auth.get('container_name')
    
    # 1. 优先立即从持久化数据中移除并保存，确保状态即刻生效
    del data[domain]
    save_data(data)
    log(f"域名 {domain} 已立即从配置文件中移除保存")
    
    # 2. 清理 Nginx 反代配置
    proxy_conf = get_proxy_conf_path(domain)
    if proxy_conf and os.path.exists(proxy_conf):
        try:
            os.remove(proxy_conf)
            reload_openresty()
        except Exception as e:
            log(f"清理站点 Nginx 配置文件异常: {e}")
        
    # 3. 异步启动后台线程清理 1Panel 站点（不影响全局 SSO 容器）
    threading.Thread(
        target=async_cleanup_domain_resources,
        args=(client_id, container_name, domain),
        daemon=True
    ).start()
    
    log(f"域名 {domain} 删除请求处理完毕，立即响应前端")
    if is_ajax:
        return jsonify({"success": True, "msg": f"已成功删除域名 {domain} 及所有关联配置"})
        
    flash('已成功删除域名及关联配置', 'success')
    return redirect(url_for('index'))

@app.route('/api/toggle/<domain>/<feature>', methods=['POST'])
def api_toggle(domain, feature):
    domain = domain.strip().lower()
    enabled_str = request.form.get('enabled', 'false')
    enabled = enabled_str.lower() == 'true'
    
    data = load_data()
    if domain not in data:
        return json.dumps({"success": False, "error": "域名配置不存在"})
        
    auth = data[domain]
    
    if 'target_host' not in auth: auth['target_host'] = '127.0.0.1'
    if 'proxy_enabled' not in auth: auth['proxy_enabled'] = True
    if 'ssl_enabled' not in auth: auth['ssl_enabled'] = False
    if 'auth_enabled' not in auth: auth['auth_enabled'] = True
    
    # 尝试从现有配置中提取目标主机与端口
    target_host = auth.get('target_host', '127.0.0.1')
    target_port = auth.get('target_port', 80)
    proxy_conf = get_proxy_conf_path(domain)
    if proxy_conf:
        try:
            with open(proxy_conf, 'r') as f:
                content = f.read()
            # 提取 proxy_pass http://host:port;
            matches = re.findall(r'proxy_pass http://([^:/;\s]+):([0-9]+);', content)
            if matches:
                oauth_port = str(auth.get('oauth_port', 4180))
                for h, p in matches:
                    if p != oauth_port:
                        target_host = h
                        target_port = int(p)
                        break
        except Exception as e:
            log(f"提取原目标地址失败: {e}")
            
    auth['target_host'] = target_host
    auth['target_port'] = target_port
            
    if feature == 'proxy':
        auth['proxy_enabled'] = enabled
        new_conf = update_nginx_config(domain, auth['oauth_port'], target_host, target_port, auth['auth_enabled'], enabled)
        if new_conf:
            auth['nginx_config'] = new_conf
            save_data(data)
            return json.dumps({"success": True, "nginx_config": new_conf})
        return json.dumps({"success": False, "error": "更新 Nginx 反代配置失败"})
        
    elif feature == 'auth':
        auth['auth_enabled'] = enabled
        new_conf = update_nginx_config(domain, auth['oauth_port'], target_host, target_port, enabled, auth['proxy_enabled'])
        if new_conf:
            auth['nginx_config'] = new_conf
            save_data(data)
            return json.dumps({"success": True, "nginx_config": new_conf})
        return json.dumps({"success": False, "error": "更新 Nginx 认证配置失败"})
        
    elif feature == 'ssl':
        ok = toggle_nginx_ssl(domain, enabled)
        if ok:
            auth['ssl_enabled'] = enabled
            save_data(data)
            return json.dumps({"success": True})
        return json.dumps({"success": False, "error": "1Panel SSL 设置失败，请确认该域名是否有可用证书"})
        
    return json.dumps({"success": False, "error": "无效的控制类型"})

@app.route('/api/domain/<domain>/auth_methods', methods=['POST'])
def api_update_domain_auth_methods(domain):
    domain = domain.strip().lower()
    data = load_data()
    if domain not in data:
        return jsonify({"success": False, "error": "域名配置不存在"})

    allow_passkey = request.form.get('allow_passkey', 'true').lower() == 'true'
    allow_password = request.form.get('allow_password', 'true').lower() == 'true'

    if not allow_passkey and not allow_password:
        return jsonify({"success": False, "error": "必须至少保留一种登录认证方式（Passkey 或密码）"})

    auth = data[domain]
    auth['allow_passkey'] = allow_passkey
    auth['allow_password'] = allow_password

    target_host = auth.get('target_host', '127.0.0.1')
    target_port = auth.get('target_port', 80)
    oauth_port = auth.get('oauth_port', GLOBAL_SSO_PORT)
    auth_enabled = auth.get('auth_enabled', True)
    proxy_enabled = auth.get('proxy_enabled', True)

    save_data(data)
    new_conf = update_nginx_config(domain, oauth_port, target_host, target_port, auth_enabled, proxy_enabled)
    if new_conf:
        auth['nginx_config'] = new_conf
        save_data(data)
        log(f"域名 {domain} 登录方式策略已更新 (Passkey: {allow_passkey}, Password: {allow_password})")
        return jsonify({
            "success": True,
            "allow_passkey": allow_passkey,
            "allow_password": allow_password,
            "nginx_config": new_conf
        })

    return jsonify({"success": False, "error": "更新 Nginx 反代配置失败"})


@app.route('/api/list')
def api_list():
    return json.dumps(load_data())


@app.route('/ssl')
def ssl_page():
    return render_template('ssl.html')

@app.route('/users')
def users_page():
    return redirect('/#users')

# ─── Keycloak 用户与角色权限管理 API ───
_USERS_CACHE = {"data": None, "expires_at": 0}
_USERS_CACHE_LOCK = threading.Lock()

def invalidate_users_cache():
    global _USERS_CACHE
    with _USERS_CACHE_LOCK:
        _USERS_CACHE["data"] = None
        _USERS_CACHE["expires_at"] = 0

@app.route('/api/users')
def api_users():
    search = request.args.get('search', '').strip()
    first = int(request.args.get('first', 0))
    max_count = int(request.args.get('max', 100))
    force = request.args.get('force', 'false').lower() in ['true', '1']
    
    # 若为常规全量列表且无搜索词，且未强制刷新，优先返回服务端短期内存缓存（30 秒有效）
    if not search and first == 0 and not force:
        now = time.time()
        with _USERS_CACHE_LOCK:
            if _USERS_CACHE["data"] and now < _USERS_CACHE["expires_at"]:
                return json.dumps(_USERS_CACHE["data"])
                
    params = {"first": first, "max": max_count, "briefRepresentation": "false"}
    if search:
        params["search"] = search
        
    data, code, err = call_keycloak_api("users", "GET", params=params)
    if code != 200 or not isinstance(data, list):
        return json.dumps({"success": False, "error": err or "获取用户列表失败", "users": []})
        
    admin_user, _, _ = get_keycloak_admin_credentials()
    
    def enrich_single_user(u):
        uid = u.get("id")
        username = u.get("username", "")
        email = u.get("email", "")
        enabled = bool(u.get("enabled", True))
        created_ts = u.get("createdTimestamp", 0)
        req_actions = u.get("requiredActions", [])
        
        has_passkey = False
        passkey_count = 0
        has_password = False
        
        # 并发查询用户绑定的凭据
        creds_data, creds_code, _ = call_keycloak_api(f"users/{uid}/credentials", "GET")
        if creds_code == 200 and isinstance(creds_data, list):
            for c in creds_data:
                ctype = c.get("type", "").lower()
                if "webauthn" in ctype:
                    has_passkey = True
                    passkey_count += 1
                elif ctype == "password":
                    has_password = True
                    
        # 并发查询用户的 Realm 角色
        roles_list = []
        is_admin = (username == admin_user)
        roles_data, roles_code, _ = call_keycloak_api(f"users/{uid}/role-mappings/realm", "GET")
        if roles_code == 200 and isinstance(roles_data, list):
            for r in roles_data:
                rname = r.get("name", "")
                if rname:
                    roles_list.append(rname)
                    if rname == "admin":
                        is_admin = True
                        
        # 解析用户站点访问权限
        attrs = u.get("attributes", {})
        allowed_sites_attr = attrs.get("allowed_sites", ["*"])
        user_sites = []
        if isinstance(allowed_sites_attr, str):
            user_sites = [s.strip() for s in allowed_sites_attr.split(",") if s.strip()]
        elif isinstance(allowed_sites_attr, list):
            for item in allowed_sites_attr:
                if isinstance(item, str):
                    for sub in item.split(","):
                        if sub.strip():
                            user_sites.append(sub.strip())
        else:
            user_sites = ["*"]
            
        if not user_sites:
            user_sites = ["*"]
            
        all_sites_access = ("*" in user_sites) or is_admin
                        
        return {
            "id": uid,
            "username": username,
            "email": email,
            "enabled": enabled,
            "created_timestamp": created_ts,
            "has_passkey": has_passkey,
            "passkey_count": passkey_count,
            "has_password": has_password,
            "required_actions": req_actions,
            "roles": roles_list,
            "is_admin": is_admin,
            "allowed_sites": user_sites,
            "all_sites_access": all_sites_access
        }

    # 使用高性能线程池并发处理所有用户的凭据与权限详情
    max_workers = min(10, max(2, len(data)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        enriched_users = list(executor.map(enrich_single_user, data))
        
    res_obj = {"success": True, "users": enriched_users, "total": len(enriched_users)}
    if not search and first == 0:
        with _USERS_CACHE_LOCK:
            _USERS_CACHE["data"] = res_obj
            _USERS_CACHE["expires_at"] = time.time() + 30
            
    return json.dumps(res_obj)

@app.route('/api/users/create', methods=['POST'])
def api_users_create():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    temporary = request.form.get('temporary', 'false').lower() in ['true', '1', 'on']
    require_passkey = request.form.get('require_passkey', 'true').lower() in ['true', '1', 'on']
    is_admin = request.form.get('is_admin', 'false').lower() in ['true', '1', 'on']
    
    if not username:
        return json.dumps({"success": False, "error": "用户名不能为空"})
        
    if not re.match(r'^[a-zA-Z0-9_\.\@\-]+$', username):
        return json.dumps({"success": False, "error": "用户名仅支持字母、数字、点、下划线和连字符"})
        
    req_actions = []
    if require_passkey:
        req_actions.append("webauthn-register-passwordless")
        
    user_payload = {
        "username": username,
        "enabled": True,
        "emailVerified": bool(email),
        "requiredActions": req_actions
    }
    if email:
        user_payload["email"] = email
        
    if password:
        user_payload["credentials"] = [{
            "type": "password",
            "value": password,
            "temporary": temporary
        }]
        
    data, code, err = call_keycloak_api("users", "POST", json_data=user_payload)
    if code not in (200, 201, 204):
        err_msg = err or "创建用户失败"
        if isinstance(data, dict) and data.get("errorMessage"):
            err_msg = data["errorMessage"]
        return json.dumps({"success": False, "error": err_msg})
        
    # 查询刚创建的用户获取其 ID
    created_id = None
    u_list, u_code, _ = call_keycloak_api("users", "GET", params={"username": username, "exact": "true"})
    if u_code == 200 and isinstance(u_list, list) and u_list:
        created_id = u_list[0].get("id")
        
    # 若勾选管理员角色，赋予 admin Realm 角色
    if created_id and is_admin:
        r_data, r_code, _ = call_keycloak_api("roles/admin", "GET")
        if r_code == 200 and isinstance(r_data, dict):
            call_keycloak_api(f"users/{created_id}/role-mappings/realm", "POST", json_data=[r_data])
            
    invalidate_users_cache()
    log(f"成功创建 Keycloak 用户: {username} (Passkey绑定预置: {require_passkey}, 管理员: {is_admin})")
    return json.dumps({"success": True, "msg": f"用户 {username} 创建成功", "user_id": created_id})

@app.route('/api/users/<user_id>/toggle', methods=['POST'])
def api_users_toggle(user_id):
    enabled_str = request.form.get('enabled', 'false')
    enabled = enabled_str.lower() in ['true', '1', 'on']
    
    admin_user, _, _ = get_keycloak_admin_credentials()
    u_data, u_code, _ = call_keycloak_api(f"users/{user_id}", "GET")
    if u_code == 200 and isinstance(u_data, dict):
        if not enabled and u_data.get("username") == admin_user:
            return json.dumps({"success": False, "error": "禁止停用系统超级管理员账号"})
            
    data, code, err = call_keycloak_api(f"users/{user_id}", "PUT", json_data={"enabled": enabled})
    if code not in (200, 204):
        return json.dumps({"success": False, "error": err or "更新用户状态失败"})
        
    invalidate_users_cache()
    sync_all_sites_permissions()
    log(f"用户状态已更新: {user_id} -> {'启用' if enabled else '停用'}")
    return json.dumps({"success": True, "enabled": enabled})

@app.route('/api/users/<user_id>/delete', methods=['POST'])
def api_users_delete(user_id):
    admin_user, _, _ = get_keycloak_admin_credentials()
    u_data, u_code, _ = call_keycloak_api(f"users/{user_id}", "GET")
    if u_code == 200 and isinstance(u_data, dict):
        if u_data.get("username") == admin_user:
            return json.dumps({"success": False, "error": "禁止删除系统超级管理员账号"})
            
    data, code, err = call_keycloak_api(f"users/{user_id}", "DELETE")
    if code not in (200, 204):
        return json.dumps({"success": False, "error": err or "删除用户失败"})
        
    invalidate_users_cache()
    sync_all_sites_permissions()
    log(f"用户已成功删除: {user_id}")
    return json.dumps({"success": True, "msg": "用户已彻底删除"})

@app.route('/api/users/<user_id>/reset_password', methods=['POST'])
def api_users_reset_password(user_id):
    new_password = request.form.get('new_password', '').strip()
    temporary = request.form.get('temporary', 'false').lower() in ['true', '1', 'on']
    require_passkey = request.form.get('require_passkey', 'false').lower() in ['true', '1', 'on']
    clear_passkey = request.form.get('clear_passkey', 'false').lower() in ['true', '1', 'on']
    
    # 1. 重置密码
    if new_password:
        pwd_payload = {
            "type": "password",
            "value": new_password,
            "temporary": temporary
        }
        _, p_code, p_err = call_keycloak_api(f"users/{user_id}/reset-password", "PUT", json_data=pwd_payload)
        if p_code not in (200, 204):
            return json.dumps({"success": False, "error": p_err or "重置密码失败"})
            
    # 2. 清除旧 Passkey 凭据（若勾选）
    if clear_passkey:
        creds_data, c_code, _ = call_keycloak_api(f"users/{user_id}/credentials", "GET")
        if c_code == 200 and isinstance(creds_data, list):
            for c in creds_data:
                if "webauthn" in c.get("type", "").lower():
                    cid = c.get("id")
                    if cid:
                        call_keycloak_api(f"users/{user_id}/credentials/{cid}", "DELETE")
                        
    # 3. 设置必填操作：要求下次登录绑定 Passkey
    if require_passkey:
        u_data, u_code, _ = call_keycloak_api(f"users/{user_id}", "GET")
        if u_code == 200 and isinstance(u_data, dict):
            actions = u_data.get("requiredActions", [])
            if "webauthn-register-passwordless" not in actions:
                actions.append("webauthn-register-passwordless")
            call_keycloak_api(f"users/{user_id}", "PUT", json_data={"requiredActions": actions})
            
    invalidate_users_cache()
    log(f"用户凭据与密码重置成功: {user_id}")
    return json.dumps({"success": True, "msg": "密码与凭据设置已成功生效"})

# ─── 角色列表内存缓存 ───
_ROLES_CACHE = {"data": None, "expires_at": 0}
_ROLES_CACHE_LOCK = threading.Lock()

@app.route('/api/roles')
def api_roles():
    now = time.time()
    with _ROLES_CACHE_LOCK:
        if _ROLES_CACHE["data"] and now < _ROLES_CACHE["expires_at"]:
            return json.dumps(_ROLES_CACHE["data"])

    data, code, err = call_keycloak_api("roles", "GET")
    if code != 200 or not isinstance(data, list):
        return json.dumps({"success": False, "error": err or "获取角色列表失败", "roles": []})
    roles = []
    for r in data:
        rname = r.get("name", "")
        if rname:
            roles.append({
                "id": r.get("id"),
                "name": rname,
                "description": r.get("description", "")
            })
    res_obj = {"success": True, "roles": roles}
    with _ROLES_CACHE_LOCK:
        _ROLES_CACHE["data"] = res_obj
        _ROLES_CACHE["expires_at"] = now + 60 # 缓存 60 秒
    return json.dumps(res_obj)


@app.route('/api/users/<user_id>/roles', methods=['POST'])
def api_users_update_roles(user_id):
    role_names_raw = request.form.get('roles', '').strip()
    target_roles = [r.strip() for r in role_names_raw.split(',') if r.strip()]
    
    # 1. 获取所有可用的 Realm 角色
    all_roles, r_code, _ = call_keycloak_api("roles", "GET")
    if r_code != 200 or not isinstance(all_roles, list):
        return json.dumps({"success": False, "error": "获取角色元数据失败"})
    role_map = {r["name"]: r for r in all_roles if "name" in r}
    
    # 2. 获取用户当前已有的 Realm 角色
    curr_roles, c_code, _ = call_keycloak_api(f"users/{user_id}/role-mappings/realm", "GET")
    if c_code != 200 or not isinstance(curr_roles, list):
        curr_roles = []
    curr_role_names = set(r["name"] for r in curr_roles if "name" in r)
    
    # 3. 计算需要新增和删除的角色
    to_add = [role_map[name] for name in target_roles if name in role_map and name not in curr_role_names]
    to_remove = [r for r in curr_roles if r.get("name") not in target_roles and r.get("name") != "default-roles-master"]
    
    if to_add:
        call_keycloak_api(f"users/{user_id}/role-mappings/realm", "POST", json_data=to_add)
    if to_remove:
        call_keycloak_api(f"users/{user_id}/role-mappings/realm", "DELETE", json_data=to_remove)
        
    invalidate_users_cache()
    log(f"用户角色权限已更新: {user_id} -> {target_roles}")
    return json.dumps({"success": True, "msg": "用户角色权限更新成功"})

@app.route('/api/users/<user_id>/sites', methods=['POST'])
def api_users_update_sites(user_id):
    sites_raw = request.form.get('sites', '*').strip()
    if sites_raw == '*' or not sites_raw:
        sites_list = ['*']
    else:
        sites_list = [s.strip() for s in sites_raw.split(',') if s.strip()]
        if not sites_list:
            sites_list = ['*']

    # 确保 Keycloak 声明式用户属性已注册 allowed_sites
    ensure_keycloak_user_profile_allowed_sites()

    u_data, u_code, u_err = call_keycloak_api(f"users/{user_id}", "GET")
    if u_code != 200 or not isinstance(u_data, dict):
        return json.dumps({"success": False, "error": u_err or "获取用户信息失败"})

    admin_user, _, _ = get_keycloak_admin_credentials()
    username = u_data.get("username", "")

    # 获取现有 attributes 并更新 allowed_sites
    attrs = u_data.get("attributes", {})
    if not isinstance(attrs, dict):
        attrs = {}
    attrs["allowed_sites"] = sites_list
    u_data["attributes"] = attrs

    p_data, p_code, p_err = call_keycloak_api(f"users/{user_id}", "PUT", json_data=u_data)
    if p_code not in (200, 204):
        return json.dumps({"success": False, "error": p_err or "更新用户站点权限失败"})

    invalidate_users_cache()
    sync_all_sites_permissions()
    log(f"用户站点访问权限已更新: {username} -> {sites_list}")
    return json.dumps({"success": True, "msg": f"用户 {username} 站点权限已成功更新", "allowed_sites": sites_list})

def init_background_startup_checks():
    """在后台异步执行开机自检与环境就绪任务（全新部署或重启时全自动初始化）"""
    def _run():
        time.sleep(2)
        try:
            # 1. 确保 Keycloak Passkey 认证流与 User Profile allowed_sites 属性支持
            setup_keycloak_passkey_flow()
            ensure_keycloak_user_profile_allowed_sites()
            
            # 2. 如果存在已配置的站点，确保全局 SSO 代理服务与 OpenResty 站点配置保持最新
            data = load_data()
            if data:
                ensure_global_sso_container()
                sync_all_sites_permissions()
        except Exception as e:
            log(f"开机自检与初始化异常 (可忽略): {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    init_background_startup_checks()
    app.run(host='0.0.0.0', port=WEB_PORT, debug=debug_mode, threaded=True)


