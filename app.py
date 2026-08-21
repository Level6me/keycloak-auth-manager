#!/usr/bin/env python3
import os, json, subprocess, secrets, string, time, re, hashlib, requests, threading
from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context, send_from_directory
from datetime import datetime
import shlex
import copy

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
ONEPANEL_API_KEY = ""
ONEPANEL_PORT = 40455
WEB_PORT = 8088
CLOUDFLARE_API_TOKEN = ""
CLOUDFLARE_SERVER_IP = ""
CLOUDFLARE_PROXIED = False

_CACHED_PUBLIC_IP = None
_CACHED_PUBLIC_IP_TIME = 0

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

def load_config():
    global KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_CONTAINER
    global WEB_PORT, ONEPANEL_API_KEY, ONEPANEL_PORT
    global CLOUDFLARE_API_TOKEN, CLOUDFLARE_SERVER_IP, CLOUDFLARE_PROXIED
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            
            raw_password = cfg.get("keycloak_password", "")
            raw_api_key = cfg.get("onepanel_api_key", "")
            raw_cf_token = cfg.get("cloudflare_api_token", "")
            
            KEYCLOAK_PASSWORD = decrypt_val(raw_password)
            ONEPANEL_API_KEY = decrypt_val(raw_api_key)
            CLOUDFLARE_API_TOKEN = decrypt_val(raw_cf_token)
            CLOUDFLARE_SERVER_IP = cfg.get("cloudflare_server_ip", "")
            CLOUDFLARE_PROXIED = bool(cfg.get("cloudflare_proxied", False))
            
            need_rewrite = False
            if raw_password and not raw_password.startswith("gAAAA"):
                cfg["keycloak_password"] = encrypt_val(raw_password)
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

def run_cmd_args(args):
    # 安全地以列表形式调用命令，不经过 Shell
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.returncode, r.stdout, r.stderr

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

def get_keycloak_admin_credentials():
    global KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_URL, KEYCLOAK_CONTAINER
    admin_user = KEYCLOAK_ADMIN
    admin_pass = KEYCLOAK_PASSWORD
    kc_url = KEYCLOAK_URL

    # 若未在配置中指定账号密码，自动从 Keycloak 容器环境变量中嗅探
    if not admin_user or not admin_pass:
        try:
            rc, out, _ = run_cmd_args(["docker", "inspect", KEYCLOAK_CONTAINER, "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
            if rc == 0 and out:
                env_map = {}
                for line in out.strip().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_map[k.strip()] = v.strip()
                if not admin_user:
                    admin_user = env_map.get("KC_BOOTSTRAP_ADMIN_USERNAME") or env_map.get("KEYCLOAK_ADMIN") or "admin"
                if not admin_pass:
                    admin_pass = env_map.get("KC_BOOTSTRAP_ADMIN_PASSWORD") or env_map.get("KEYCLOAK_ADMIN_PASSWORD") or ""
        except Exception:
            pass

    # 若 Keycloak 公共 URL 未指定，尝试从已运行的 oauth2 容器中嗅探 Issuer URL
    if not kc_url:
        try:
            rc, out, _ = run_cmd_args(["docker", "ps", "-a", "--filter", "name=oauth2-", "--format", "{{.Names}}"])
            if rc == 0 and out:
                for cname in out.strip().splitlines():
                    cname = cname.strip()
                    if cname:
                        rc_i, out_i, _ = run_cmd_args(["docker", "inspect", cname, "--format", "{{range .Config.Env}}{{println .}}{{end}}"])
                        if rc_i == 0 and out_i:
                            for line in out_i.splitlines():
                                if line.startswith("OAUTH2_PROXY_OIDC_ISSUER_URL="):
                                    iss = line.split("=", 1)[1].strip()
                                    if "/realms/" in iss:
                                        kc_url = iss.split("/realms/")[0].rstrip("/")
                                        break
                    if kc_url:
                        break
        except Exception:
            pass

    if not kc_url:
        kc_url = "http://127.0.0.1:8080"

    if not kc_url.startswith("http://") and not kc_url.startswith("https://"):
        kc_url = "https://" + kc_url
    kc_url = kc_url.rstrip("/")

    return admin_user or "admin", admin_pass or "", kc_url

def setup_keycloak_passkey_flow():
    admin_user, admin_pass, kc_base = get_keycloak_admin_credentials()
    if not admin_pass:
        return None

    # 获取 Token (优先使用内部直连地址 http://127.0.0.1:8080，如失败再尝试公共 URL)
    endpoints = ["http://127.0.0.1:8080"]
    if kc_base not in endpoints:
        endpoints.append(kc_base)

    token = None
    active_base = None
    for base in endpoints:
        token_url = f"{base}/realms/master/protocol/openid-connect/token"
        try:
            res = requests.post(token_url, data={
                "client_id": "admin-cli",
                "username": admin_user,
                "password": admin_pass,
                "grant_type": "password"
            }, timeout=6)
            if res.status_code == 200:
                token = res.json().get("access_token")
                if token:
                    active_base = base
                    break
        except Exception:
            continue

    if not token or not active_base:
        log("提示: 暂未连接到 Keycloak API (可忽略)，跳过 Passkey 自定义认证流配置")
        return None

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        api_base = f"{active_base}/admin/realms/master/authentication"
        
        # 1. 强制注册时绑定 Passkey
        req_actions_url = f"{api_base}/required-actions"
        actions_res = requests.get(req_actions_url, headers=headers, timeout=6)
        if actions_res.status_code == 200:
            for action in actions_res.json():
                if action.get("alias") == "webauthn-register-passwordless":
                    action["enabled"] = True
                    action["defaultAction"] = True
                    requests.put(f"{req_actions_url}/{action['alias']}", headers=headers, json=action, timeout=6)
                    log("成功将 WebAuthn Passwordless 设为注册时的默认必填项")
                    break

        # 2. 检查或创建专属的 passkey-only-browser 流
        flows_res = requests.get(f"{api_base}/flows", headers=headers, timeout=6)
        if flows_res.status_code == 200:
            flows = flows_res.json()
            existing_flow = next((f for f in flows if f.get("alias") == "passkey-only-browser"), None)
            if existing_flow:
                return existing_flow["id"]
                
        # 创建 Flow
        requests.post(f"{api_base}/flows", headers=headers, json={
            "alias": "passkey-only-browser",
            "providerId": "basic-flow",
            "topLevel": True,
            "builtIn": False,
            "description": "Auth manager passkey only flow"
        }, timeout=6)
        
        # 获取新创建的 Flow ID
        flows_res = requests.get(f"{api_base}/flows", headers=headers, timeout=6)
        if flows_res.status_code != 200:
            return None
        flows = flows_res.json()
        new_flow_id = next((f["id"] for f in flows if f.get("alias") == "passkey-only-browser"), None)
        if not new_flow_id:
            return None
        
        # 添加执行器: auth-cookie
        requests.post(f"{api_base}/flows/passkey-only-browser/executions/execution", headers=headers, json={"provider": "auth-cookie"}, timeout=6)
        # 添加执行器: webauthn-authenticator-passwordless
        requests.post(f"{api_base}/flows/passkey-only-browser/executions/execution", headers=headers, json={"provider": "webauthn-authenticator-passwordless"}, timeout=6)
        
        # 将其 requirement 改为 ALTERNATIVE
        execs_res = requests.get(f"{api_base}/flows/passkey-only-browser/executions", headers=headers, timeout=6)
        if execs_res.status_code == 200:
            for ex in execs_res.json():
                ex["requirement"] = "ALTERNATIVE"
                requests.put(f"{api_base}/flows/passkey-only-browser/executions", headers=headers, json=ex, timeout=6)
                
        log("成功创建 passkey-only-browser 自定义认证流")
        return new_flow_id
        
    except Exception as e:
        log(f"设置 Passkey 认证流异常: {e}")
        return None

def create_keycloak_client(domain, client_id, client_secret):
    log("创建 Keycloak Client: {}".format(client_id))
    
    admin_user, admin_pass, _ = get_keycloak_admin_credentials()
    
    # 确保 Passkey 配置已就绪并获取 Flow ID
    passkey_flow_id = setup_keycloak_passkey_flow()
    
    # 无需 shlex.quote 转义，直接通过参数隔离规避命令注入
    cred_rc, cred_out, cred_err = run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "config", "credentials",
        "--server", "http://localhost:8080",
        "--realm", "master",
        "--user", admin_user,
        "--password", admin_pass
    ])
    if cred_rc != 0:
        return False, f"Keycloak 登录验证失败: {cred_err.strip()}"
    
    redirect_uri = "https://" + domain + "/*"
    cmd = [
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "create", "clients",
        "-r", "master",
        "-s", f"clientId={client_id}",
        "-s", f"secret={client_secret}",
        "-s", "enabled=true",
        "-s", "publicClient=false",
        "-s", "protocol=openid-connect",
        "-s", "standardFlowEnabled=true",
        "-s", "directAccessGrantsEnabled=true",
    ]
    if passkey_flow_id:
        cmd.extend(["-s", f"authenticationFlowBindingOverrides={{\"browser\":\"{passkey_flow_id}\"}}"])
    cmd.extend([
        "-s", f"redirectUris=[\"{redirect_uri}\"]"
    ])
    create_rc, create_out, create_err = run_cmd_args(cmd)
    if create_rc != 0:
        if "already exists" in create_err:
            log("Client 已存在，更新 Secret...")
            uuid_rc, uuid_out, uuid_err = run_cmd_args([
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
                up_rc, up_out, up_err = run_cmd_args([
                    "docker", "exec", KEYCLOAK_CONTAINER,
                    "/opt/keycloak/bin/kcadm.sh", "update", f"clients/{uuid}",
                    "-r", "master",
                    "-s", f"secret={client_secret}"
                ])
                if up_rc == 0:
                    log("Secret 更新成功")
                    return True, ""
                else:
                    return False, f"更新Secret失败: {up_err.strip()}"
            else:
                return False, f"获取Client UUID失败: {uuid_err.strip()}"
        return False, f"创建Client失败: {create_err.strip()}"
    return True, ""

def delete_keycloak_client(client_id):
    log("删除 Keycloak Client: {}".format(client_id))
    run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "config", "credentials",
        "--server", "http://localhost:8080",
        "--realm", "master",
        "--user", KEYCLOAK_ADMIN,
        "--password", KEYCLOAK_PASSWORD
    ])
    
    uuid_rc, uuid_out, uuid_err = run_cmd_args([
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
        log("Keycloak Client 删除完成")
    else:
        log("未找到对应的 Client UUID，跳过删除")

def stop_oauth2_container(container_name):
    if not container_name:
        return
    log(f"停止并强制销毁容器: {container_name}")
    run_cmd_args(["docker", "rm", "-f", container_name])

def create_oauth2_container(domain, oauth_port, client_id, client_secret):
    container_name = "oauth2-" + domain.replace(".", "-")
    cookie_secret = generate_secret(32)
    log("创建容器: {} (端口 {})".format(container_name, oauth_port))
    
    _, _, kc_issuer_base = get_keycloak_admin_credentials()
    
    run_cmd_args(["docker", "rm", "-f", container_name])
    
    run_args = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", "always",
        "--network", "host",
        "-e", "OAUTH2_PROXY_PROVIDER=oidc",
        "-e", f"OAUTH2_PROXY_OIDC_ISSUER_URL={kc_issuer_base}/realms/master",
        "-e", f"OAUTH2_PROXY_CLIENT_ID={client_id}",
        "-e", f"OAUTH2_PROXY_CLIENT_SECRET={client_secret}",
        "-e", f"OAUTH2_PROXY_REDIRECT_URL=https://{domain}/oauth2/callback",
        "-e", f"OAUTH2_PROXY_COOKIE_SECRET={cookie_secret}",
        "-e", "OAUTH2_PROXY_COOKIE_SECURE=true",
        "-e", "OAUTH2_PROXY_SKIP_PROVIDER_BUTTON=true",
        "-e", "OAUTH2_PROXY_CODE_CHALLENGE_METHOD=S256",
        "-e", "OAUTH2_PROXY_EMAIL_DOMAINS=*",
        "-e", "OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true",
        "-e", "OAUTH2_PROXY_USER_ID_CLAIM=preferred_username",
        "-e", f"OAUTH2_PROXY_HTTP_ADDRESS=0.0.0.0:{oauth_port}",
        "quay.io/oauth2-proxy/oauth2-proxy:v7.6.0"
    ]
    
    rc, out, err = run_cmd_args(run_args)
    if rc != 0:
        log("容器失败: {}".format(err.strip()))
        return False, container_name, cookie_secret, err.strip()
    log("容器创建成功")
    return True, container_name, cookie_secret, ""

def get_proxy_conf_path(domain):
    if not domain:
        return None
    domain = domain.strip().lower()
    base_dirs = [
        f"/opt/1panel/apps/openresty/openresty/www/sites/{domain}",
        f"/opt/1panel/www/sites/{domain}"
    ]
    # 先检查是否已有存在的目录
    for b in base_dirs:
        if os.path.exists(b):
            proxy_dir = os.path.join(b, "proxy")
            os.makedirs(proxy_dir, exist_ok=True)
            return os.path.join(proxy_dir, "root.conf")
            
    # 如果不存在，确定 OpenResty 的 sites 父目录并自愈创建
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

def update_nginx_config(domain, oauth_port, target_host, target_port, auth_enabled, proxy_enabled):
    proxy_conf = get_proxy_conf_path(domain)
    if not proxy_conf:
        log("未找到 OpenResty 站点目录，无法生成反代配置文件")
        return None
    
    target_host = target_host.strip() if target_host else "127.0.0.1"
    target_upstream = f"{target_host}:{target_port}"
        
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
location ^~ / {{
    proxy_pass http://{};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}}
""".format(target_upstream)
    else:
        # 完整认证反代
        new_content = """# OAuth2 认证路径 - 需要大缓冲区处理 cookie
location ^~ /oauth2/ {{
    proxy_pass http://127.0.0.1:{};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # 增加缓冲区大小，解决 oauth2 callback header 太大问题
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
}}

location = /oauth2/auth {{
    internal;
    proxy_pass http://127.0.0.1:{}/oauth2/auth;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}}

location @login {{
    return 302 https://{}/oauth2/sign_in?rd=$request_uri;
}}

# 主内容 - 需要认证
location ^~ / {{
    auth_request /oauth2/auth;
    error_page 401 = @login;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    
    proxy_pass http://{};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}}
""".format(oauth_port, oauth_port, domain, target_upstream)

    try:
        with open(proxy_conf, 'w') as f:
            f.write(new_content)
        
        # 重载 Nginx / OpenResty 容器
        or_rc, or_out, or_err = run_cmd_args(["docker", "ps", "-q", "-f", "name=openresty"])
        openresty_id = or_out.strip().splitlines()[0].strip() if or_out.strip() else ""
        if openresty_id:
            run_cmd_args(["docker", "exec", openresty_id, "nginx", "-t"])
            run_cmd_args(["docker", "exec", openresty_id, "nginx", "-s", "reload"])
            log("OpenResty / Nginx 站点配置已更新并成功重载！")
        return new_content
    except Exception as e:
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
        flash('配置已成功保存！如果您修改了“面板监听端口 (web_port)”，需手动在服务器终端执行 "sudo systemctl restart auth-manager.service" 才能生效。', 'success')
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
    try:
        port = int(port)
    except Exception:
        return json.dumps({"success": False, "error": "端口必须是数字"})
    
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
    
    client_id = domain.replace(".", "-")
    client_secret = generate_secret(32)
    
    log(f"开始配置 {domain} (目标地址: {target_host}:{port})...")
    
    used = get_used_ports()
    log(f"已用端口: {list(used)}")
    
    oauth_port = 4180
    while oauth_port in used:
        oauth_port += 1
    log(f"分配 OAuth 端口: {oauth_port}")
    
    ok, err = create_keycloak_client(domain, client_id, client_secret)
    if not ok:
        return json.dumps({"success": False, "error": f"Keycloak: {err}"})
    
    ok, cid, csecret, err = create_oauth2_container(domain, oauth_port, client_id, client_secret)
    if not ok:
        delete_keycloak_client(client_id)
        return json.dumps({"success": False, "error": err})
    
    conf = create_nginx_auth(domain, oauth_port, target_host, port)
    if not conf:
        log("Nginx 配置失败，请手动检查")
    
    fresh_data = load_data()
    fresh_data[domain] = {
        'client_id': client_id, 
        'client_secret': client_secret, 
        'cookie_secret': csecret, 
        'oauth_port': oauth_port,
        'target_host': target_host,
        'target_port': port,
        'container_name': cid, 
        'nginx_config': conf, 
        'created_at': datetime.now().isoformat(),
        'proxy_enabled': True,
        'ssl_enabled': check_domain_ssl_enabled(domain),
        'auth_enabled': True
    }
    save_data(fresh_data)
    
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
        log("🎉 认证配置完成!")
        
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
        "--filter", f"name={auth['container_name']}", 
        "--format", "{{.Status}}"
    ])
    auth['status'] = out.strip() or "未运行"
    return render_template('detail.html', domain=domain, auth=auth)

def async_cleanup_domain_resources(client_id, container_name, domain):
    """在后台线程中异步彻底清理 Keycloak Client 与 1Panel 站点，避免阻塞 Web 响应导致超时"""
    if container_name:
        try:
            stop_oauth2_container(container_name)
        except Exception as e:
            log(f"[后台释放] 删除容器 {container_name} 异常: {e}")
            
    if client_id:
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
    container_name = auth.get('container_name') or f"oauth2-{domain.replace('.', '-')}"
    
    # 1. 优先立即从持久化数据中移除并保存，确保状态即刻生效
    del data[domain]
    save_data(data)
    log(f"域名 {domain} 已立即从配置文件中移除保存")
    
    # 2. 立即极速停止本地 Docker 容器 (通常 < 0.2 秒)
    try:
        stop_oauth2_container(container_name)
    except Exception as e:
        log(f"快速停止容器异常: {e}")
        
    # 3. 异步启动后台线程清理耗时的 Keycloak 和 1Panel 站点（耗时 10-20 秒，不阻塞用户界面）
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

@app.route('/api/list')
def api_list():
    return json.dumps(load_data())

@app.route('/ssl')
def ssl_page():
    return render_template('ssl.html')

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=WEB_PORT, debug=debug_mode, threaded=True)
