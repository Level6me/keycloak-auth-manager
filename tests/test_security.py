import os
import sys
import unittest
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    is_valid_domain,
    is_valid_target_host,
    encrypt_val,
    decrypt_val,
    _is_trusted_proxy_ip,
    get_root_domain,
    CIPHER_AVAILABLE
)

class SecurityRegressionTestSuite(unittest.TestCase):

    def test_domain_validation(self):
        """验证 S7: 域名白名单格式正则防路径遍历"""
        # 合法域名
        self.assertTrue(is_valid_domain("example.com"))
        self.assertTrue(is_valid_domain("sub.example.com"))
        self.assertTrue(is_valid_domain("a-b.c-d.org"))
        self.assertTrue(is_valid_domain("my-site-123.abab.pw"))

        # 恶意/非法域名（路径遍历、注入、特殊字符）
        self.assertFalse(is_valid_domain("../evil.com"))
        self.assertFalse(is_valid_domain("example.com/../../etc/passwd"))
        self.assertFalse(is_valid_domain("example.com; rm -rf /"))
        self.assertFalse(is_valid_domain("example.com\\test"))
        self.assertFalse(is_valid_domain("example.com\n\r"))
        self.assertFalse(is_valid_domain(""))
        self.assertFalse(is_valid_domain(None))
        self.assertFalse(is_valid_domain("   "))

    def test_target_host_validation(self):
        """验证 S8 / N3: 后端目标主机格式校验（支持 IPv4, IPv6, localhost, 域名，拒绝注入）"""
        # 合法目标主机
        self.assertTrue(is_valid_target_host("127.0.0.1"))
        self.assertTrue(is_valid_target_host("192.168.1.100"))
        self.assertTrue(is_valid_target_host("10.0.0.5"))
        self.assertTrue(is_valid_target_host("localhost"))
        self.assertTrue(is_valid_target_host("internal.local"))
        self.assertTrue(is_valid_target_host("api.backend.service"))
        # IPv6
        self.assertTrue(is_valid_target_host("::1"))
        self.assertTrue(is_valid_target_host("[::1]"))
        self.assertTrue(is_valid_target_host("2001:db8::1"))
        self.assertTrue(is_valid_target_host("[2001:db8::1]"))

        # 注入攻击/非法字符
        self.assertFalse(is_valid_target_host("127.0.0.1; proxy_pass http://evil.com;"))
        self.assertFalse(is_valid_target_host("127.0.0.1\nserver { listen 80; }"))
        self.assertFalse(is_valid_target_host("127.0.0.1\r\n"))
        self.assertFalse(is_valid_target_host("127.0.0.1 { dangerous }"))
        self.assertFalse(is_valid_target_host("127.0.0.1 $remote_addr"))
        self.assertFalse(is_valid_target_host("127.0.0.1 evil"))
        self.assertFalse(is_valid_target_host(""))
        self.assertFalse(is_valid_target_host(None))

    def test_trusted_proxy_ip(self):
        """验证 S6 / N2: 可信代理网段判断"""
        self.assertTrue(_is_trusted_proxy_ip("127.0.0.1"))
        self.assertTrue(_is_trusted_proxy_ip("::1"))
        self.assertTrue(_is_trusted_proxy_ip("10.0.0.1"))
        self.assertTrue(_is_trusted_proxy_ip("192.168.1.1"))
        self.assertTrue(_is_trusted_proxy_ip("172.20.0.2"))

        # 公网直连 IP（不应被当作可信反代）
        self.assertFalse(_is_trusted_proxy_ip("8.8.8.8"))
        self.assertFalse(_is_trusted_proxy_ip("1.1.1.1"))
        self.assertFalse(_is_trusted_proxy_ip("43.108.18.47"))

    def test_password_encryption_and_config_keys(self):
        """验证 N1: 密码加密与配置字典兼容读取"""
        test_pass = "MySecureP@ssw0rd!2026"
        enc = encrypt_val(test_pass)
        self.assertNotEqual(enc, test_pass)
        self.assertEqual(decrypt_val(enc), test_pass)

        # 验证同时从 console_password 或 admin_password 中读取
        cfg1 = {"console_password": enc}
        cfg2 = {"admin_password": enc}
        cfg3 = {"console_password": enc, "admin_password": enc}

        pwd1 = cfg1.get("console_password", "") or cfg1.get("admin_password", "")
        pwd2 = cfg2.get("console_password", "") or cfg2.get("admin_password", "")
        pwd3 = cfg3.get("console_password", "") or cfg3.get("admin_password", "")

        self.assertEqual(decrypt_val(pwd1), test_pass)
        self.assertEqual(decrypt_val(pwd2), test_pass)
        self.assertEqual(decrypt_val(pwd3), test_pass)

    def test_real_load_config_integration(self):
        """验证 N1 集成测试：调用真实的 load_config()，验证仅写 admin_password 或 console_password 均能正确加载 ADMIN_PASSWORD"""
        import tempfile
        import app

        original_config_file = app.CONFIG_FILE
        test_pass = "IntegrationTestP@ss2026"
        enc_pass = encrypt_val(test_pass)

        # 场景 1: 仅配置 admin_password (模拟向导写入)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"admin_password": enc_pass, "keycloak_password": ""}, tf)
            tmp_path1 = tf.name

        try:
            app.CONFIG_FILE = tmp_path1
            app.ADMIN_PASSWORD = ""
            app.load_config()
            self.assertEqual(app.ADMIN_PASSWORD, test_pass)
        finally:
            if os.path.exists(tmp_path1):
                os.remove(tmp_path1)

        # 场景 2: 仅配置 console_password (模拟旧版或设置页写入)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"console_password": enc_pass, "keycloak_password": ""}, tf)
            tmp_path2 = tf.name

        try:
            app.CONFIG_FILE = tmp_path2
            app.ADMIN_PASSWORD = ""
            app.load_config()
            self.assertEqual(app.ADMIN_PASSWORD, test_pass)
        finally:
            if os.path.exists(tmp_path2):
                os.remove(tmp_path2)

        # 场景 3: 明文写入触发自动加密
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump({"console_password": test_pass, "keycloak_password": ""}, tf)
            tmp_path3 = tf.name

        try:
            app.CONFIG_FILE = tmp_path3
            app.ADMIN_PASSWORD = ""
            app.load_config()
            self.assertEqual(app.ADMIN_PASSWORD, test_pass)
            # 验证文件已被加密回写
            with open(tmp_path3, 'r') as f:
                saved_cfg = json.load(f)
            self.assertTrue(saved_cfg.get('console_password', '').startswith('gAAAA') or not CIPHER_AVAILABLE)
        finally:
            if os.path.exists(tmp_path3):
                os.remove(tmp_path3)
            app.CONFIG_FILE = original_config_file

    def test_root_domain_extraction(self):
        """验证 A6: 根域名自适应提取"""
        self.assertEqual(get_root_domain("ips.abab.pw"), ".abab.pw")
        self.assertEqual(get_root_domain("app.service.example.org"), ".example.org")
        self.assertEqual(get_root_domain("example.com"), ".example.com")

    def test_path_b_sso_port_routing(self):
        """验证路径 B: 纯 Passkey 站点分流至 4181，混合/密码站点分流至 4180"""
        from app import get_domain_sso_port, GLOBAL_SSO_PORT, GLOBAL_PASSKEY_SSO_PORT

        # 纯 Passkey 站点 (仅 Passkey，无密码)
        pure_passkey_site = {"allow_passkey": True, "allow_password": False}
        self.assertEqual(get_domain_sso_port(pure_passkey_site), GLOBAL_PASSKEY_SSO_PORT)
        self.assertEqual(get_domain_sso_port(pure_passkey_site), 4181)

        # 混合站点 (同时允许 Passkey 和密码)
        hybrid_site = {"allow_passkey": True, "allow_password": True}
        self.assertEqual(get_domain_sso_port(hybrid_site), GLOBAL_SSO_PORT)
        self.assertEqual(get_domain_sso_port(hybrid_site), 4180)

        # 纯密码站点 (仅密码)
        password_only_site = {"allow_passkey": False, "allow_password": True}
        self.assertEqual(get_domain_sso_port(password_only_site), GLOBAL_SSO_PORT)
        self.assertEqual(get_domain_sso_port(password_only_site), 4180)

        # 默认缺省值
        default_site = {}
        self.assertEqual(get_domain_sso_port(default_site), GLOBAL_SSO_PORT)

    def test_oidc_endpoints_and_validation(self):
        """验证 OIDC 模块端点生成与安全保留字/格式规则"""
        from app import get_standard_oidc_endpoints, SYSTEM_RESERVED_CLIENT_IDS
        import re

        endpoints = get_standard_oidc_endpoints()
        self.assertIn("issuer", endpoints)
        self.assertIn("discovery_url", endpoints)
        self.assertIn("authorization_endpoint", endpoints)
        self.assertIn("token_endpoint", endpoints)
        self.assertIn("userinfo_endpoint", endpoints)
        self.assertTrue(endpoints["discovery_url"].endswith("/.well-known/openid-configuration"))

        # 验证保留名保护
        self.assertIn("admin-cli", SYSTEM_RESERVED_CLIENT_IDS)
        self.assertIn("realm-management", SYSTEM_RESERVED_CLIENT_IDS)

        # 验证 client_id 正则
        pattern = r'^[a-zA-Z0-9_-]{2,50}$'
        self.assertTrue(bool(re.match(pattern, "wordpress")))
        self.assertTrue(bool(re.match(pattern, "my_gitlab_app")))
        self.assertFalse(bool(re.match(pattern, "a")))
        self.assertFalse(bool(re.match(pattern, "bad id with space")))
        self.assertFalse(bool(re.match(pattern, "bad/slash")))
        self.assertFalse(bool(re.match(pattern, "inject;drop")))

    def test_decrypt_val_fallback_and_plaintext(self):
        """验证解密明文透传与损坏密文在 fallback_empty=True 时安全回退为空串"""
        self.assertEqual(decrypt_val("plain-secret"), "plain-secret")
        if CIPHER_AVAILABLE:
            bad_token = "gAAAAABinvalid_corrupted_token_payload_1234567890"
            self.assertEqual(decrypt_val(bad_token, fallback_empty=True), "")

    def test_csrf_json_array_and_login_username(self):
        """验证 JSON 数组请求体不触发 500 崩溃，且自定义管理员名时拒绝硬编码 admin"""
        import app as kam_app
        from unittest.mock import patch

        client = kam_app.app.test_client()
        with patch.object(kam_app, "ADMIN_USERNAME", "custom_ops"), \
             patch.object(kam_app, "KEYCLOAK_ADMIN", "kc_ops"), \
             patch.object(kam_app, "ADMIN_PASSWORD", "StrongPass!23"):
            with client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user"] = "custom_ops"
                sess["csrf_token"] = "valid-token"

            res_csrf = client.post(
                "/api/ssl/import",
                data=json.dumps([{"primary_domain": "a.com"}]),
                content_type="application/json"
            )
            self.assertEqual(res_csrf.status_code, 403)

            client.post("/logout")
            res_login_bad = client.post(
                "/login",
                data={"username": "admin", "password": "StrongPass!23"},
                follow_redirects=False
            )
            self.assertEqual(res_login_bad.status_code, 200)
            self.assertIn("用户名或密码错误", res_login_bad.get_data(as_text=True))

            res_init = client.post("/api/init_password", json={"password": "NewPassword123", "password_confirm": "NewPassword123"})
            self.assertEqual(res_init.status_code, 409)

    def test_ensure_global_sso_pure_passkey_routing_and_pagination(self):
        """验证新建纯 Passkey 站点正确分流到 global-sso-passkey 且 Keycloak 分页不截断"""
        import app as kam_app
        from unittest.mock import patch

        recorded_calls = []

        def fake_ensure_client(client_id, flow_id, secret_cfg_key, target_domains, extra_domain=None, extra_ssl_enabled=None):
            recorded_calls.append((client_id, list(target_domains), extra_domain))
            return True, "", "dummy-secret"

        with patch.object(kam_app, "setup_keycloak_adaptive_sso_flow", return_value={"hybrid": "f1", "passkey_only": "f2"}), \
             patch.object(kam_app, "load_data", return_value={}), \
             patch.object(kam_app, "_ensure_specific_sso_client", side_effect=fake_ensure_client), \
             patch.object(kam_app, "_ensure_single_sso_container", return_value=(True, "")), \
             patch.object(kam_app, "get_all_cookie_and_whitelist_domains", return_value=(".example.com", "*.example.com")):
            ok, err = kam_app.ensure_global_sso_container(
                extra_domain="pk.example.com",
                extra_ssl_enabled=True,
                extra_allow_passkey=True,
                extra_allow_password=False
            )
            self.assertTrue(ok, err)
            by_cid = {cid: (domains, extra) for cid, domains, extra in recorded_calls}
            self.assertNotIn("pk.example.com", by_cid[kam_app.GLOBAL_SSO_CLIENT_ID][0])
            self.assertIsNone(by_cid[kam_app.GLOBAL_SSO_CLIENT_ID][1])
            self.assertIn("pk.example.com", by_cid[kam_app.GLOBAL_PASSKEY_SSO_CLIENT_ID][0])
            self.assertEqual(by_cid[kam_app.GLOBAL_PASSKEY_SSO_CLIENT_ID][1], "pk.example.com")

        # 验证分页拉取超过 100 名用户时不被截断
        users_page_1 = [{"username": f"u{i}", "enabled": True, "attributes": {"allowed_sites": ["*"]}} for i in range(200)]
        users_page_2 = [{"username": "restricted_u", "enabled": True, "attributes": {"allowed_sites": ["other.com"]}},
                        {"username": "u201", "enabled": True, "attributes": {"allowed_sites": ["app.example.com"]}}]

        def fake_call_kc(endpoint, method="GET", json_data=None, params=None):
            if endpoint == "users" and params:
                return (users_page_1 if params.get("first", 0) == 0 else users_page_2), 200, ""
            return [], 200, ""

        with patch.object(kam_app, "call_keycloak_api", side_effect=fake_call_kc), \
             patch.object(kam_app, "get_keycloak_admin_credentials", return_value=("admin", "pw", "http://127.0.0.1:8080")):
            all_allowed, allowed_list = kam_app.get_allowed_users_for_domain("app.example.com")
            self.assertFalse(all_allowed)
            self.assertIn("u201", allowed_list)
            self.assertNotIn("restricted_u", allowed_list)

    def test_settings_checkbox_uncheck_and_shared_guards(self):
        """验证 /settings 取消勾选 cloudflare_proxied 正确保存为 False，且 Passkey 共享资源受保护"""
        import tempfile
        import app as kam_app
        from unittest.mock import patch

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump({"cloudflare_proxied": True}, tf)
            tmp_cfg = tf.name

        orig_cfg = kam_app.CONFIG_FILE
        try:
            kam_app.CONFIG_FILE = tmp_cfg
            kam_app._save_settings_from_dict({"has_cloudflare_proxied_field": "1"})
            with open(tmp_cfg, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertFalse(saved["cloudflare_proxied"])
        finally:
            kam_app.CONFIG_FILE = orig_cfg
            if os.path.exists(tmp_cfg):
                os.remove(tmp_cfg)

        with patch.object(kam_app, "run_cmd_args") as mock_cmd:
            kam_app.delete_keycloak_client(kam_app.GLOBAL_PASSKEY_SSO_CLIENT_ID)
            kam_app.stop_oauth2_container(kam_app.GLOBAL_PASSKEY_SSO_CONTAINER)
            mock_cmd.assert_not_called()

    def test_403_root_causes_prevention(self):
        """验证认证后 403 根因修复：admin角色放行、大小写不敏感、API失败不覆写配置、新建用户触发同步、api_list脱敏"""
        import tempfile
        import app as kam_app
        from unittest.mock import patch

        users_sample = [
            {"username": "Alice", "enabled": True, "attributes": {"allowed_sites": ["App.Example.com"]}},
            {"username": "ops_admin", "enabled": True, "attributes": {"allowed_sites": ["other.com"]}},
            {"username": "Bob", "enabled": True, "attributes": {"allowed_sites": ["other.com"]}},
        ]

        def fake_kc(endpoint, method="GET", json_data=None, params=None):
            if endpoint == "users":
                return users_sample, 200, ""
            if endpoint == "roles/admin/users":
                return [{"username": "ops_admin"}], 200, ""
            return [], 200, ""

        with patch.object(kam_app, "call_keycloak_api", side_effect=fake_kc), \
             patch.object(kam_app, "get_keycloak_admin_credentials", return_value=("SuperAdmin", "pw", "https://auth.example.com")):
            all_ok, allowed = kam_app.get_allowed_users_for_domain("app.example.com")
            self.assertFalse(all_ok)
            self.assertIn("alice", allowed)
            self.assertIn("ops_admin", allowed)
            self.assertIn("superadmin", allowed)
            self.assertNotIn("bob", allowed)

        # Keycloak 失败时 sync_all_sites_permissions 必须直接中止，不得调用 update_nginx_config
        with patch.object(kam_app, "load_data", return_value={"app.example.com": {"proxy_enabled": True}}), \
             patch.object(kam_app, "_fetch_all_keycloak_items", return_value=(None, 500, "down")), \
             patch.object(kam_app, "update_nginx_config") as mock_upd:
            self.assertFalse(kam_app.sync_all_sites_permissions())
            mock_upd.assert_not_called()

        # 验证 /api/list 剔除了旧密钥字段但保留 nginx_config
        sample_data = {"app.example.com": {"client_secret": "sec", "cookie_secret": "csec", "nginx_config": "cfg", "oauth_port": 4180}}
        client = kam_app.app.test_client()
        with patch.object(kam_app, "ADMIN_PASSWORD", "StrongPass!23"), \
             patch.object(kam_app, "load_data", return_value=sample_data):
            with client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user"] = kam_app.ADMIN_USERNAME
                sess["csrf_token"] = "tok"
            res = client.get("/api/list")
            self.assertEqual(res.status_code, 200)
            body = json.loads(res.get_data(as_text=True))
            site = body["app.example.com"]
            self.assertNotIn("client_secret", site)
            self.assertNotIn("cookie_secret", site)
            self.assertEqual(site.get("nginx_config"), "cfg")

        # 验证生成的 Nginx 配置包含 /oauth2/auth 大缓冲区、Lua string.lower 与 OIDC_EMAIL_CLAIM
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_file = os.path.join(tmpdir, "root.conf")
            with patch.object(kam_app, "get_proxy_conf_path", return_value=conf_file), \
                 patch.object(kam_app, "load_data", return_value={"app.example.com": {}}), \
                 patch.object(kam_app, "get_allowed_users_for_domain", return_value=(False, ["alice"])), \
                 patch.object(kam_app, "get_keycloak_admin_credentials", return_value=("admin", "pw", "https://auth.example.com")), \
                 patch.object(kam_app, "reload_openresty", return_value=True):
                conf_txt = kam_app.update_nginx_config("app.example.com", 4180, "127.0.0.1", 8080, True, True)
                self.assertIn("string.lower", conf_txt)
                self.assertIn("location = /oauth2/auth", conf_txt)
                self.assertIn("proxy_buffer_size 128k;", conf_txt)
                self.assertIn("client_max_body_size 0;", conf_txt)
                self.assertIn('proxy_set_header X-Original-URL "";', conf_txt)
                self.assertIn('proxy_set_header X-Forwarded-Preferred-Username "";', conf_txt)

    def test_bypass_hardening_empty_sites_proxy_isolation_and_logout(self):
        """验证绕过防护：空 allowed_sites 拒绝访问、冲突 proxy/*.conf 隔离与回滚、停用/删号即时 logout"""
        import tempfile
        import app as kam_app
        from unittest.mock import patch

        # 1. 显式设置 allowed_sites=[] 必须拒绝访问，不得反转成 *
        users_empty_sites = [
            {"username": "revoked_user", "enabled": True, "attributes": {"allowed_sites": []}},
            {"username": "normal_user", "enabled": True, "attributes": {}},
        ]

        def fake_kc(endpoint, method="GET", json_data=None, params=None):
            if endpoint == "users":
                return users_empty_sites, 200, ""
            if endpoint == "roles/admin/users":
                return [], 200, ""
            return [], 200, ""

        with patch.object(kam_app, "call_keycloak_api", side_effect=fake_kc), \
             patch.object(kam_app, "get_keycloak_admin_credentials", return_value=("admin", "pw", "https://auth.example.com")):
            all_ok, allowed = kam_app.get_allowed_users_for_domain("app.example.com")
            self.assertFalse(all_ok)
            self.assertNotIn("revoked_user", allowed)
            self.assertIn("normal_user", allowed)

        # 2. 同级冲突 proxy/*.conf 自动隔离，并在 update_nginx_config 失败时还原
        with tempfile.TemporaryDirectory() as tmpdir:
            root_conf = os.path.join(tmpdir, "root.conf")
            conflict_conf = os.path.join(tmpdir, "legacy-bypass.conf")
            with open(conflict_conf, "w", encoding="utf-8") as f:
                f.write("location / { proxy_pass http://127.0.0.1:9999; }")

            with patch.object(kam_app, "ONEPANEL_API_KEY", ""), \
                 patch.object(kam_app, "ensure_openresty_site_conf"), \
                 patch.object(kam_app, "get_proxy_conf_path", return_value=root_conf), \
                 patch.object(kam_app, "_audit_1panel_site_security"):
                with patch.object(kam_app, "update_nginx_config", return_value="ok_conf"):
                    res = kam_app.create_nginx_auth("app.example.com", 4180, "127.0.0.1", 8080)
                    self.assertEqual(res, "ok_conf")
                    self.assertFalse(os.path.exists(conflict_conf))
                    self.assertTrue(os.path.exists(conflict_conf + ".kam-disabled"))

                # 恢复冲突文件并测试失败回滚
                os.replace(conflict_conf + ".kam-disabled", conflict_conf)
                with patch.object(kam_app, "update_nginx_config", return_value=None):
                    res_fail = kam_app.create_nginx_auth("app.example.com", 4180, "127.0.0.1", 8080)
                    self.assertIsNone(res_fail)
                    self.assertTrue(os.path.exists(conflict_conf))

        # 3. 停用或删除用户时立即吊销 Keycloak 会话 (logout)
        kc_calls = []

        def fake_user_ops(endpoint, method="GET", json_data=None, params=None):
            kc_calls.append((endpoint, method))
            if endpoint == "users/u-123" and method == "GET":
                return {"id": "u-123", "username": "bob"}, 200, ""
            return {}, 204, ""

        client = kam_app.app.test_client()
        with patch.object(kam_app, "ADMIN_PASSWORD", "StrongPass!23"), \
             patch.object(kam_app, "call_keycloak_api", side_effect=fake_user_ops), \
             patch.object(kam_app, "sync_all_sites_permissions", return_value=True):
            with client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user"] = kam_app.ADMIN_USERNAME
                sess["csrf_token"] = "tok"

            res_dis = client.post("/api/users/u-123/toggle", data={"enabled": "false", "_csrf_token": "tok"})
            self.assertEqual(res_dis.status_code, 200)
            self.assertIn(("users/u-123/logout", "POST"), kc_calls)

            kc_calls.clear()
            res_del = client.post("/api/users/u-123/delete", data={"_csrf_token": "tok"})
            self.assertEqual(res_del.status_code, 200)
            self.assertIn(("users/u-123/logout", "POST"), kc_calls)
            self.assertLess(kc_calls.index(("users/u-123/logout", "POST")), kc_calls.index(("users/u-123", "DELETE")))

    def test_oidc_client_crud_standards_and_sorting(self):
        """验证 OIDC 应用 CRUD 符合标准：password_only支持、ROPC禁用、+与##注销白名单、大小写规范化与系统前置排序"""
        import tempfile
        import app as kam_app
        from unittest.mock import patch

        endpoints = kam_app.get_standard_oidc_endpoints()
        for key in ("issuer", "discovery_url", "authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri", "end_session_endpoint"):
            self.assertIn(key, endpoints)

        # 1. 验证 URI 解析与注销白名单规则
        r_uris, origins, logout_attr, err = kam_app._parse_oidc_client_uris("https://blog.example.com/cb", "")
        self.assertIsNone(err)
        self.assertEqual(r_uris, ["https://blog.example.com/cb"])
        self.assertEqual(origins, ["https://blog.example.com"])
        self.assertEqual(logout_attr, "+")

        _, _, logout_plus, err_plus = kam_app._parse_oidc_client_uris("https://blog.example.com/cb", "+")
        self.assertIsNone(err_plus)
        self.assertEqual(logout_plus, "+")

        _, _, logout_multi, err_multi = kam_app._parse_oidc_client_uris(
            "https://blog.example.com/cb",
            "https://blog.example.com/logout1##https://blog.example.com/logout2"
        )
        self.assertIsNone(err_multi)
        self.assertEqual(logout_multi, "https://blog.example.com/logout1##https://blog.example.com/logout2")

        _, _, _, err_cross = kam_app._parse_oidc_client_uris("https://blog.example.com/cb", "https://evil.com/logout")
        self.assertIsNotNone(err_cross)

        # 2. 验证创建/更新/列表接口行为
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_file = os.path.join(tmpdir, "oidc_clients.json")
            created_payloads = []
            updated_payloads = []
            flows = [
                {"id": "flow-hybrid", "alias": "global-sso-browser"},
                {"id": "flow-pk", "alias": "passkey-only-browser"},
                {"id": "flow-pw", "alias": "password-only-browser"},
            ]
            kc_clients = [
                {"id": "sys-1", "clientId": kam_app.GLOBAL_SSO_CLIENT_ID, "name": "Global SSO", "publicClient": False, "redirectUris": ["https://a.com/*"], "webOrigins": ["https://a.com"], "authenticationFlowBindingOverrides": {"browser": "flow-hybrid"}, "attributes": {}},
                {"id": "app-old", "clientId": "old_app", "name": "Old App", "publicClient": False, "redirectUris": ["https://old.com/cb"], "webOrigins": ["https://old.com"], "authenticationFlowBindingOverrides": {"browser": "flow-pw"}, "attributes": {"post.logout.redirect.uris": "+"}},
            ]

            def fake_fetch_all(endpoint, params=None):
                if endpoint == "clients":
                    return kc_clients, 200, ""
                return [], 200, ""

            def fake_call_kc(endpoint, method="GET", json_data=None, params=None):
                if endpoint == "authentication/flows" and method == "GET":
                    return flows, 200, ""
                if endpoint == "clients" and method == "GET":
                    cid = (params or {}).get("clientId")
                    return [c for c in kc_clients if c.get("clientId") == cid], 200, ""
                if endpoint == "clients" and method == "POST":
                    created_payloads.append(json_data)
                    new_obj = dict(json_data)
                    new_obj["id"] = f"id-{json_data['clientId']}"
                    kc_clients.append(new_obj)
                    return {"id": new_obj["id"]}, 201, ""
                if endpoint.startswith("clients/") and endpoint.endswith("/client-secret") and method == "GET":
                    return {"value": "mock-secret"}, 200, ""
                if endpoint.startswith("clients/") and method == "PUT":
                    updated_payloads.append(json_data)
                    return {}, 204, ""
                return {}, 200, ""

            client = kam_app.app.test_client()
            with patch.object(kam_app, "OIDC_CLIENTS_FILE", meta_file), \
                 patch.object(kam_app, "ADMIN_PASSWORD", "StrongPass!23"), \
                 patch.object(kam_app, "_fetch_all_keycloak_items", side_effect=fake_fetch_all), \
                 patch.object(kam_app, "call_keycloak_api", side_effect=fake_call_kc):
                with client.session_transaction() as sess:
                    sess["logged_in"] = True
                    sess["user"] = kam_app.ADMIN_USERNAME
                    sess["csrf_token"] = "tok"

                # 创建含大写 client_id 且 auth_method=password_only、注销白名单=+
                res_create = client.post("/api/oidc/clients", data={
                    "_csrf_token": "tok",
                    "name": "Wiki App",
                    "client_id": "MyWiki",
                    "auth_method": "password_only",
                    "redirect_uris": "https://wiki.example.com/callback",
                    "post_logout_redirect_uris": "+",
                })
                self.assertEqual(res_create.status_code, 200)
                body_create = json.loads(res_create.get_data(as_text=True))
                self.assertTrue(body_create["success"])
                self.assertEqual(body_create["client_id"], "mywiki")
                self.assertEqual(len(created_payloads), 1)
                self.assertFalse(created_payloads[0]["directAccessGrantsEnabled"])
                self.assertEqual(created_payloads[0]["authenticationFlowBindingOverrides"]["browser"], "flow-pw")
                self.assertEqual(created_payloads[0]["attributes"]["post.logout.redirect.uris"], "+")

                # 更新应用，提交多条注销地址
                res_upd = client.put("/api/oidc/clients/MyWiki", data={
                    "_csrf_token": "tok",
                    "name": "Wiki App Updated",
                    "auth_method": "hybrid",
                    "redirect_uris": "https://wiki.example.com/callback",
                    "post_logout_redirect_uris": "https://wiki.example.com/out1\nhttps://wiki.example.com/out2",
                })
                self.assertEqual(res_upd.status_code, 200)
                self.assertFalse(updated_payloads[0]["directAccessGrantsEnabled"])
                self.assertEqual(updated_payloads[0]["authenticationFlowBindingOverrides"]["browser"], "flow-hybrid")
                self.assertEqual(updated_payloads[0]["attributes"]["post.logout.redirect.uris"], "https://wiki.example.com/out1##https://wiki.example.com/out2")

                # 验证列表排序（系统客户端在前）与 password_only 推断
                res_list = client.get("/api/oidc/clients")
                self.assertEqual(res_list.status_code, 200)
                clients_list = json.loads(res_list.get_data(as_text=True))["clients"]
                self.assertTrue(clients_list[0]["is_system"])
                old_item = next(c for c in clients_list if c["client_id"] == "old_app")
                self.assertEqual(old_item["auth_method"], "password_only")

if __name__ == '__main__':
    unittest.main()
