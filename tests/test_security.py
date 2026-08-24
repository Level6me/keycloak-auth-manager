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
    get_root_domain
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

if __name__ == '__main__':
    unittest.main()
