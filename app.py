#!/usr/bin/env python3
import os, json, subprocess, secrets, string, time, re
from flask import Flask, render_template, request, redirect, url_for, flash, Response, stream_with_context
from datetime import datetime

# 配置文件路径
CONFIG_FILE = "/opt/keycloak-auth-manager/config.json"
DATA_FILE = "/opt/keycloak-auth-manager/data.json"

# 配置变量（从 config.json 加载，无默认值）
KEYCLOAK_URL = ""
KEYCLOAK_ADMIN = ""
KEYCLOAK_PASSWORD = ""
KEYCLOAK_CONTAINER = "keycloak"

def load_config():
    global KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD, KEYCLOAK_CONTAINER
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                KEYCLOAK_URL = cfg.get("keycloak_url", "")
                KEYCLOAK_ADMIN = cfg.get("keycloak_admin", "")
                KEYCLOAK_PASSWORD = cfg.get("keycloak_password", "")
                KEYCLOAK_CONTAINER = cfg.get("keycloak_container", "keycloak")
    except Exception as e:
        print("加载配置失败:", str(e))

load_config()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
current_logs = []

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_secret(length=32):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def log(msg):
    line = "[{}] {}".format(datetime.now().strftime("%H:%M:%S"), msg)
    current_logs.append(line)
    print(line)

def run_cmd(cmd):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.returncode, r.stdout, r.stderr

def get_used_ports():
    rc, out, err = run_cmd("netstat -tlnp | grep ':418' | awk '{print $4}' | grep -oE '[0-9]+$'")
    ports = set()
    for p in out.strip().split('\n'):
        if p: ports.add(int(p))
    return ports

def create_keycloak_client(domain, client_id, client_secret):
    log("创建 Keycloak Client: {}".format(client_id))
    # 使用配置变量
    run_cmd("docker exec {} /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user {} --password {}".format(KEYCLOAK_CONTAINER, KEYCLOAK_ADMIN, KEYCLOAK_PASSWORD))
    
    redirect_uri = "https://" + domain + "/*"
    cmd = 'docker exec {} /opt/keycloak/bin/kcadm.sh create clients -r master -s clientId={} -s secret={} -s enabled=true -s publicClient=false -s protocol=openid-connect -s standardFlowEnabled=true -s directAccessGrantsEnabled=true -s \'redirectUris=["{}"]\''.format(KEYCLOAK_CONTAINER, client_id, client_secret, redirect_uri)
    
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        if "already exists" in err:
            log("Client 已存在，更新 Secret...")
def create_oauth2_container(domain, oauth_port, client_id, client_secret):
    container_name = "oauth2-" + domain.replace(".", "-")
    cookie_secret = generate_secret(32)
    log("创建容器: {} (端口 {})".format(container_name, oauth_port))
    
    run_cmd("docker rm -f " + container_name)
    
    cmd = "docker run -d --name {} --restart always --network host -e OAUTH2_PROXY_PROVIDER=oidc -e OAUTH2_PROXY_OIDC_ISSUER_URL=" + KEYCLOAK_URL + "/realms/master -e OAUTH2_PROXY_CLIENT_ID={} -e OAUTH2_PROXY_CLIENT_SECRET={} -e OAUTH2_PROXY_REDIRECT_URL=https://{} -e OAUTH2_PROXY_COOKIE_SECRET={} -e OAUTH2_PROXY_COOKIE_SECURE=true -e OAUTH2_PROXY_SKIP_PROVIDER_BUTTON=true -e OAUTH2_PROXY_CODE_CHALLENGE_METHOD=S256 -e OAUTH2_PROXY_EMAIL_DOMAINS=* -e OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true -e OAUTH2_PROXY_USER_ID_CLAIM=preferred_username -e OAUTH2_PROXY_HTTP_ADDRESS=0.0.0.0:{} quay.io/oauth2-proxy/oauth2-proxy:v7.6.0".format(container_name, client_id, client_secret, domain + "/oauth2/callback", cookie_secret, oauth_port)
    
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        log("容器失败: {}".format(err))
        return False, container_name, cookie_secret, err
    log("容器创建成功")
    return True, container_name, cookie_secret, ""

def stop_oauth2_container(container_name):
    run_cmd("docker rm -f " + container_name)

def create_nginx_auth(domain, oauth_port):
    log("修改 Nginx 配置...")
    
    proxy_conf = "/opt/1panel/apps/openresty/openresty/www/sites/" + domain + "/proxy/root.conf"
    
    if not os.path.exists(proxy_conf):
        log("未找到 1Panel 配置文件，请先在 1Panel 创建网站")
        return None
    
    # 读取现有配置获取目标端口
    with open(proxy_conf, 'r') as f:
        content = f.read()
    
    target_port = "8080"
    old_proxy_match = re.search(r'proxy_pass http://127\.0\.0\.1:([0-9]+)', content)
    if old_proxy_match:
        target_port = old_proxy_match.group(1)
        log("目标端口: {}".format(target_port))
    
    # 生成配置 - 包含 proxy buffer 解决 header 太大的问题
    new_content = '''# OAuth2 认证路径 - 需要大缓冲区处理 cookie
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
'''.format(oauth_port, oauth_port, domain, target_port)
    
    with open(proxy_conf, 'w') as f:
        f.write(new_content)
    
    log("Nginx 配置已更新（包含 proxy buffer 设置）")
    
    run_cmd("docker exec $(docker ps -q -f name=openresty) nginx -t")
    run_cmd("docker exec $(docker ps -q -f name=openresty) nginx -s reload")
    log("Nginx 已重载")
    
    return proxy_conf

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
    
    ok, cn, cs, err = create_oauth2_container(domain, oauth_port, client_id, client_secret)
    if not ok:
        delete_keycloak_client(client_id)
        return json.dumps({"success": False, "error": "Docker: {}".format(err)})
    
    nginx = create_nginx_auth(domain, oauth_port)
    if not nginx:
        log("Nginx 配置失败，请手动添加")
    
    log("完成!")
    
    data[domain] = {'client_id': client_id, 'client_secret': client_secret, 'cookie_secret': cs, 'oauth_port': oauth_port, 'container_name': cn, 'nginx_config': nginx, 'created_at': datetime.now().isoformat()}
    save_data(data)
    return json.dumps({"success": True})

@app.route('/detail/<domain>')
def detail(domain):
    data = load_data()
    if domain not in data: return redirect(url_for('index'))
    auth = data[domain]
    rc, out, err = run_cmd("docker ps --filter name={} --format \"{{.Status}}\"".format(auth['container_name']))
    auth['status'] = out.strip() or "未运行"
    return render_template('detail.html', domain=domain, auth=auth)

@app.route('/delete/<domain>', methods=['POST'])
def delete(domain):
    data = load_data()
    if domain not in data: return redirect(url_for('index'))
    auth = data[domain]
    delete_keycloak_client(auth['client_id'])
    stop_oauth2_container(auth['container_name'])
    del data[domain]
    save_data(data)
    flash('已删除', 'success')
    return redirect(url_for('index'))

@app.route('/api/list')
def api_list():
    return json.dumps(load_data())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088, debug=False, threaded=True)
