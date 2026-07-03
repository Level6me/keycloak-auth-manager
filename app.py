#!/usr/bin/env python3
import os, json, subprocess, secrets, string, time, re, hashlib, requests
from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context
from datetime import datetime
from cryptography.fernet import Fernet
import shlex
import copy

# 配置文件路径
CONFIG_FILE = "/opt/keycloak-auth-manager/config.json"
DATA_FILE = "/opt/keycloak-auth-manager/data.json"
ENCRYPTION_KEY_FILE = "/opt/keycloak-auth-manager/encryption.key"

# 加密密钥初始化
if not os.path.exists(ENCRYPTION_KEY_FILE):
    os.makedirs('/opt/keycloak-auth-manager', exist_ok=True)
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, 'wb') as f:
        f.write(key)
    try:
        os.chmod(ENCRYPTION_KEY_FILE, 0o600)
    except Exception:
        pass

with open(ENCRYPTION_KEY_FILE, 'rb') as f:
    fernet_key = f.read().strip()
cipher = Fernet(fernet_key)

def encrypt_val(val):
    if not val: return ""
    try:
        return cipher.encrypt(val.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print("加密失败:", str(e))
        return val

def decrypt_val(val):
    if not val: return ""
    try:
        return cipher.decrypt(val.encode('utf-8')).decode('utf-8')
    except Exception as e:
        # 如果解密失败，说明是明文，直接返回原值以实现兼容
        return val

# 配置变量（从 config.json 加载，无默认值）
KEYCLOAK_URL = ""
KEYCLOAK_ADMIN = ""
KEYCLOAK_PASSWORD = ""
KEYCLOAK_CONTAINER = "keycloak"
ONEPANEL_API_KEY = ""
ONEPANEL_PORT = 40455
WEB_PORT = 8088

def load_config():
    global KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_CONTAINER
    global WEB_PORT, ONEPANEL_API_KEY, ONEPANEL_PORT
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            
            raw_password = cfg.get("keycloak_password", "")
            raw_api_key = cfg.get("onepanel_api_key", "")
            
            KEYCLOAK_PASSWORD = decrypt_val(raw_password)
            ONEPANEL_API_KEY = decrypt_val(raw_api_key)
            
            need_rewrite = False
            if raw_password and not raw_password.startswith("gAAAA"):
                cfg["keycloak_password"] = encrypt_val(raw_password)
                need_rewrite = True
            if raw_api_key and not raw_api_key.startswith("gAAAA"):
                cfg["onepanel_api_key"] = encrypt_val(raw_api_key)
                need_rewrite = True
                
            KEYCLOAK_URL = cfg.get("keycloak_url", "")
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
# 修复：使用固定的或持久化的 secret_key
if not os.path.exists('/opt/keycloak-auth-manager/secret.key'):
    os.makedirs('/opt/keycloak-auth-manager', exist_ok=True)
    with open('/opt/keycloak-auth-manager/secret.key', 'w') as f:
        f.write(secrets.token_hex(32))
with open('/opt/keycloak-auth-manager/secret.key', 'r') as f:
    app.secret_key = f.read().strip()
current_logs = []

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            for domain, auth in data.items():
                if isinstance(auth, dict):
                    if 'client_secret' in auth:
                        auth['client_secret'] = decrypt_val(auth['client_secret'])
                    if 'cookie_secret' in auth:
                        auth['cookie_secret'] = decrypt_val(auth['cookie_secret'])
                    
                    # 默认状态注入与向前兼容
                    if 'proxy_enabled' not in auth:
                        auth['proxy_enabled'] = True
                    if 'auth_enabled' not in auth:
                        auth['auth_enabled'] = True
                    if 'ssl_enabled' not in auth:
                        nginx_conf = auth.get('nginx_config', '')
                        if nginx_conf and ('https' in nginx_conf or '443' in nginx_conf or 'ssl' in nginx_conf):
                            auth['ssl_enabled'] = True
                        else:
                            auth['ssl_enabled'] = False
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
    line = "[{}] {}".format(datetime.now().strftime("%H:%M:%S"), msg)
    current_logs.append(line)
    print(line)

def run_cmd_args(args):
    # 安全地以列表形式调用命令，不经过 Shell
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.returncode, r.stdout, r.stderr

def get_used_ports():
    rc, out, err = run_cmd_args(["netstat", "-tlnp"])
    ports = set()
    if rc == 0:
        for line in out.splitlines():
            # 匹配本地绑定端口，例如包含 :418x
            match = re.search(r':(418\d+)\b', line)
            if match:
                ports.add(int(match.group(1)))
    
    # 额外检查 data.json 中已经分配出去的端口（防止容器崩溃时释放端口导致重复分配）
    data = load_data()
    for k, v in data.items():
        if isinstance(v, dict) and 'oauth_port' in v:
            ports.add(int(v['oauth_port']))
            
    return ports

def call_1panel_api(endpoint, method="POST", payload=None):
    if not ONEPANEL_API_KEY:
        log("警告: 未配置 1Panel API Key，跳过 API 调用")
        return None
    ts = str(int(time.time()))
    token = hashlib.md5(("1panel" + ONEPANEL_API_KEY + ts).encode()).hexdigest()
    headers = {
        "1Panel-Token": token,
        "1Panel-Timestamp": ts,
        "Content-Type": "application/json"
    }
    url = f"http://127.0.0.1:{ONEPANEL_PORT}{endpoint}"
    try:
        if method == "POST":
            res = requests.post(url, headers=headers, json=payload, timeout=10)
        else:
            res = requests.get(url, headers=headers, params=payload, timeout=10)
        return res.json()
    except Exception as e:
        log(f"1Panel API 错误: {e}")
        return None

def create_keycloak_client(domain, client_id, client_secret):
    log("创建 Keycloak Client: {}".format(client_id))
    
    # 无需 shlex.quote 转义，直接通过参数隔离规避命令注入
    cred_rc, cred_out, cred_err = run_cmd_args([
        "docker", "exec", KEYCLOAK_CONTAINER,
        "/opt/keycloak/bin/kcadm.sh", "config", "credentials",
        "--server", "http://localhost:8080",
        "--realm", "master",
        "--user", KEYCLOAK_ADMIN,
        "--password", KEYCLOAK_PASSWORD
    ])
    if cred_rc != 0:
        return False, f"Keycloak 登录验证失败: {cred_err.strip()}"
    
    redirect_uri = "https://" + domain + "/*"
    create_rc, create_out, create_err = run_cmd_args([
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
        "-s", f"redirectUris=[\"{redirect_uri}\"]"
    ])
    
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
            uuid = uuid_out.strip()
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
    uuid = uuid_out.strip()
    if uuid:
        run_cmd_args([
            "docker", "exec", KEYCLOAK_CONTAINER,
            "/opt/keycloak/bin/kcadm.sh", "delete", f"clients/{uuid}",
            "-r", "master"
        ])
        log("Keycloak Client 删除完成")
    else:
        log("未找到对应的 Client UUID，跳过删除")

def create_oauth2_container(domain, oauth_port, client_id, client_secret):
    container_name = "oauth2-" + domain.replace(".", "-")
    cookie_secret = generate_secret(32)
    log("创建容器: {} (端口 {})".format(container_name, oauth_port))
    
    run_cmd_args(["docker", "rm", "-f", container_name])
    
    run_args = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", "always",
        "--network", "host",
        "-e", "OAUTH2_PROXY_PROVIDER=oidc",
        "-e", f"OAUTH2_PROXY_OIDC_ISSUER_URL={KEYCLOAK_URL}/realms/master",
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

def stop_oauth2_container(container_name):
    run_cmd_args(["docker", "rm", "-f", container_name])

def update_nginx_config(domain, oauth_port, target_port, auth_enabled, proxy_enabled):
    proxy_conf = "/opt/1panel/apps/openresty/openresty/www/sites/" + domain + "/proxy/root.conf"
    if not os.path.exists(proxy_conf):
        log("未找到 1Panel 配置文件，请确认网站创建成功")
        return None
        
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
    proxy_pass http://127.0.0.1:{};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}}
""".format(target_port)
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
}}

location @login {{
    return 302 https://{}/oauth2/sign_in?rd=$request_uri;
}}

# 主内容 - 需要认证
location ^~ / {{
    auth_request /oauth2/auth;
    error_page 401 = @login;
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    
    proxy_pass http://127.0.0.1:{};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
}}
""".format(oauth_port, oauth_port, domain, target_port)

    try:
        with open(proxy_conf, 'w') as f:
            f.write(new_content)
        
        # 重载 Nginx 容器
        or_rc, or_out, or_err = run_cmd_args(["docker", "ps", "-q", "-f", "name=openresty"])
        openresty_id = or_out.strip()
        if openresty_id:
            run_cmd_args(["docker", "exec", openresty_id, "nginx", "-t"])
            run_cmd_args(["docker", "exec", openresty_id, "nginx", "-s", "reload"])
            log("Nginx 站点配置已更新并重载！")
        return new_content
    except Exception as e:
        log(f"更新 Nginx 配置文件失败: {str(e)}")
        return None

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
        ssl_res = call_1panel_api("/api/v1/websites/ssl/search", "POST", {"page": 1, "pageSize": 100})
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
        "websiteId": ws_id,
        "enable": enable,
        "websiteSSLId": ssl_id,
        "type": "existed" if ssl_id else "local",
        "httpConfig": "HTTPToHTTPS" if enable else "none",
        "httpsPorts": [443]
    }
    res = call_1panel_api(f"/api/v1/websites/{ws_id}/https", "POST", https_payload)
    if res and res.get("code") == 200:
        log(f"1Panel SSL 设置成功（状态: {enable}）")
        return True
    log(f"1Panel SSL 设置失败: {res}")
    return False

def create_nginx_auth(domain, oauth_port, target_port):
    log("修改 Nginx 配置...")
    
    # 尝试通过 1Panel API 自动建站
    api_payload = {
        "primaryDomain": domain,
        "type": "proxy",
        "alias": domain,
        "webSiteGroupID": 1,
        "domains": [{"domain": domain, "port": 80}],
        "appType": "installed",
        "proxy": f"http://127.0.0.1:{target_port}",
        "remark": "Keycloak Auth Manager 自动创建"
    }
    res = call_1panel_api("/api/v1/websites", "POST", api_payload)
    if res and res.get("code") == 200:
        log("通过 1Panel API 成功创建反向代理网站")
        # 等待一秒让文件系统同步
        time.sleep(1.5)
    else:
        if res:
            log(f"1Panel API 创建建站失败，尝试继续修改配置文件. 响应: {res}")
        else:
            log("跳过 1Panel API 调用")
    
    proxy_conf = "/opt/1panel/apps/openresty/openresty/www/sites/" + domain + "/proxy/root.conf"
    
    if not os.path.exists(proxy_conf):
        log("未找到 1Panel 配置文件，请确认网站创建成功")
        return None
    
    with open(proxy_conf, 'r') as f:
        content = f.read()
    
    old_proxy_match = re.search(r'proxy_pass http://127\.0\.0\.1:([0-9]+)', content)
    if old_proxy_match:
        found_port = old_proxy_match.group(1)
        log("检测到原目标端口: {}".format(found_port))
    
    new_conf = update_nginx_config(domain, oauth_port, target_port, auth_enabled=True, proxy_enabled=True)
    return new_conf

@app.route('/')
def index():
    return render_template('index.html', auths=load_data())

@app.route('/add')
def add_page():
    return render_template('add.html')

@app.route('/api/logs')
def api_logs():
    def gen():
        while True:
            if current_logs:
                for l in current_logs: yield "data: {}\n\n".format(l)
                current_logs[:] = []
            yield "data: heartbeat\n\n"
            time.sleep(0.5)
    return Response(stream_with_context(gen()), mimetype='text/event-stream')

@app.route('/api/acme_accounts')
def api_acme_accounts():
    res = call_1panel_api("/api/v1/websites/acme/search", "POST", {"page":1, "pageSize":100})
    accounts = []
    if res and res.get("code") == 200 and res.get("data") and res["data"].get("items"):
        for item in res["data"]["items"]:
            accounts.append({"id": item["id"], "email": item["email"]})
    return json.dumps(accounts)

@app.route('/api/dns_accounts')
def api_dns_accounts():
    res = call_1panel_api("/api/v1/websites/dns/search", "POST", {"page":1, "pageSize":100})
    accounts = []
    if res and res.get("code") == 200 and res.get("data") and res["data"].get("items"):
        for item in res["data"]["items"]:
            accounts.append({"id": item["id"], "name": item["name"]})
    return json.dumps(accounts)

@app.route('/api/create', methods=['POST'])
def api_create():
    current_logs[:] = []
    domain = request.form.get('domain', '').strip()
    port = request.form.get('port', '').strip()
    
    if not domain or not port:
        return json.dumps({"success": False, "error": "域名和端口必填"})
    try: port = int(port)
    except: return json.dumps({"success": False, "error": "端口必须是数字"})
    
    data = load_data()
    if domain in data:
        return json.dumps({"success": False, "error": "该域名已配置"})
    
    client_id = domain.replace(".", "-")
    client_secret = generate_secret(32)
    
    log("开始配置 {}...".format(domain))
    
    used = get_used_ports()
    log("已用端口: {}".format(list(used)))
    
    oauth_port = 4180
    while oauth_port in used: oauth_port += 1
    log("分配端口: {}".format(oauth_port))
    
    ok, err = create_keycloak_client(domain, client_id, client_secret)
    if not ok:
        return json.dumps({"success": False, "error": "Keycloak: {}".format(err)})
    
    ok, cid, csecret, err = create_oauth2_container(domain, oauth_port, client_id, client_secret)
    if not ok:
        delete_keycloak_client(client_id)
        return json.dumps({"success": False, "error": err})
    
    conf = create_nginx_auth(domain, oauth_port, port)
    if not conf:
        log("Nginx 配置失败，请手动添加")
    
    log("完成!")
    
    fresh_data = load_data()
    fresh_data[domain] = {
        'client_id': client_id, 
        'client_secret': client_secret, 
        'cookie_secret': csecret, 
        'oauth_port': oauth_port, 
        'container_name': cid, 
        'nginx_config': conf, 
        'created_at': datetime.now().isoformat(),
        'proxy_enabled': True,
        'ssl_enabled': False,
        'auth_enabled': True
    }
    save_data(fresh_data)
    return json.dumps({"success": True})

@app.route('/api/apply_ssl', methods=['POST'])
def api_apply_ssl():
    current_logs[:] = []
    domain = request.form.get('domain', '').strip()
    acme_id = request.form.get('acme_id')
    dns_id = request.form.get('dns_id')
    
    if not domain or not acme_id:
        return json.dumps({"success": False, "error": "参数不足"})
        
    log(f"开始为 {domain} 申请 SSL 证书...")
    
    ssl_payload = {
        "primaryDomain": domain,
        "provider": "dnsAccount" if dns_id else "http",
        "acmeAccountId": int(acme_id),
        "autoRenew": True,
        "description": "Auto SSL by KAM",
        "apply": True,
        "keyType": "P256",
    }
    if dns_id:
        ssl_payload["dnsAccountId"] = int(dns_id)
    
    log("正在向 1Panel 提交 SSL 申请...")
    ssl_res = call_1panel_api("/api/v1/websites/ssl", "POST", ssl_payload)
    if ssl_res and ssl_res.get("code") == 200:
        ssl_id = ssl_res["data"]["id"]
        log(f"申请已提交，等待证书签发中 (此过程可能需要 1-3 分钟)...")
        # 轮询等待 SSL 就绪
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
        
        for _ in range(36): # wait up to 3 minutes
            time.sleep(5)
            
            # 尝试寻找并读取1Panel的SSL申请日志并输出
            last_log_size, log_file = read_1panel_log(last_log_size, log_file)

            # 使用 pageSize=100 并且不依赖接口内置的 domain 过滤参数以防由于过滤失效被分页吞掉
            search_res = call_1panel_api("/api/v1/websites/ssl/search", "POST", {"page": 1, "pageSize": 100})
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
                        # 让前端有时间拉取最后一条SSE日志
                        time.sleep(2)
                        return json.dumps({"success": False, "error": f"1Panel API返回失败状态: {err_msg}"})
        
        if ssl_ready:
            log("正在将证书绑定 to 网站并开启 HTTPS...")
            ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
            if ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]:
                ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
                if ws_item:
                    ws_id = ws_item["id"]
                    https_payload = {
                        "websiteId": ws_id,
                        "enable": True,
                        "websiteSSLId": ssl_id,
                        "type": "existed",
                        "httpConfig": "HTTPToHTTPS",
                        "httpsPorts": [443]
                    }
                    call_1panel_api(f"/api/v1/websites/{ws_id}/https", "POST", https_payload)
                    log("HTTPS 绑定成功，网站配置已重载！")
                    log("全部完成!")
                    
                    # 同步将本地 ssl_enabled 状态设为 True
                    fresh_data = load_data()
                    if domain in fresh_data:
                        fresh_data[domain]['ssl_enabled'] = True
                        save_data(fresh_data)
                        
                    return json.dumps({"success": True})
            log(f"绑定失败：未能找到对应的反代网站信息。API 响应: {ws_res}")
            return json.dumps({"success": False, "error": "未找到对应的反代网站信息"})
    else:
        err_msg = f"提交 SSL 申请失败: {ssl_res.get('message', '未知错误') if ssl_res else '无响应'}"
        log(err_msg)
        return json.dumps({"success": False, "error": err_msg})
        
    return json.dumps({"success": False, "error": "证书申请超过3分钟超时，请去1Panel后台查看详情"})

@app.route('/detail/<domain>')
def detail(domain):
    data = load_data()
    if domain not in data: return redirect(url_for('index'))
    auth = data[domain]
    
    # 实时从 1Panel 查询此站点的 HTTPS 开启状态，修复：加入 OrderBy 和 Order 必填字段支持 API 成功拉取
    ws_res = call_1panel_api("/api/v1/websites/search", "POST", {"page": 1, "pageSize": 10, "info": domain, "orderBy": "created_at", "order": "null"})
    if ws_res and ws_res.get("code") == 200 and ws_res.get("data") and ws_res["data"]["items"]:
        ws_item = next((x for x in ws_res["data"]["items"] if x.get("primaryDomain") == domain or domain in x.get("domains", [])), None)
        if ws_item:
            # 1Panel 启用了 HTTPS 时，protocol 为 "HTTPS"
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

@app.route('/delete/<domain>', methods=['POST'])
def delete(domain):
    log(f"收到删除请求，domain: '{domain}'")
    data = load_data()
    if domain not in data: 
        log("域名不在数据中，直接返回")
        return redirect(url_for('index'))
    auth = data[domain]
    try:
        delete_keycloak_client(auth['client_id'])
    except Exception as e:
        log(f"删除 keycloak client 异常: {e}")
    try:
        stop_oauth2_container(auth['container_name'])
    except Exception as e:
        log(f"停止容器异常: {e}")
    
    fresh_data = load_data()
    if domain in fresh_data:
        del fresh_data[domain]
        save_data(fresh_data)
        
    log("删除并保存成功")
    flash('已删除', 'success')
    return redirect(url_for('index'))

@app.route('/api/toggle/<domain>/<feature>', methods=['POST'])
def api_toggle(domain, feature):
    enabled_str = request.form.get('enabled', 'false')
    enabled = enabled_str.lower() == 'true'
    
    data = load_data()
    if domain not in data:
        return json.dumps({"success": False, "error": "域名配置不存在"})
        
    auth = data[domain]
    
    if 'proxy_enabled' not in auth: auth['proxy_enabled'] = True
    if 'ssl_enabled' not in auth: auth['ssl_enabled'] = False
    if 'auth_enabled' not in auth: auth['auth_enabled'] = True
    
    target_port = 80
    proxy_conf = "/opt/1panel/apps/openresty/openresty/www/sites/" + domain + "/proxy/root.conf"
    if os.path.exists(proxy_conf):
        try:
            with open(proxy_conf, 'r') as f:
                content = f.read()
            matches = re.findall(r'proxy_pass http://127\.0\.0\.1:([0-9]+)', content)
            if matches:
                oauth_port = auth.get('oauth_port', 4180)
                for m in matches:
                    if int(m) != int(oauth_port):
                        target_port = int(m)
                        break
                else:
                    target_port = int(matches[-1])
        except Exception as e:
            log(f"提取原目标端口失败: {e}")
            
    if feature == 'proxy':
        auth['proxy_enabled'] = enabled
        new_conf = update_nginx_config(domain, auth['oauth_port'], target_port, auth['auth_enabled'], enabled)
        if new_conf:
            auth['nginx_config'] = new_conf
            save_data(data)
            return json.dumps({"success": True, "nginx_config": new_conf})
        return json.dumps({"success": False, "error": "更新 Nginx 反代配置失败"})
        
    elif feature == 'auth':
        auth['auth_enabled'] = enabled
        new_conf = update_nginx_config(domain, auth['oauth_port'], target_port, enabled, auth['proxy_enabled'])
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
    app.run(host='0.0.0.0', port=WEB_PORT, debug=True, threaded=True)
