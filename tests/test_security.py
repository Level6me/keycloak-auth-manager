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

    def test_root_domain_extraction(self):
        """验证 A6: 根域名自适应提取"""
        self.assertEqual(get_root_domain("ips.abab.pw"), ".abab.pw")
        self.assertEqual(get_root_domain("app.service.example.org"), ".example.org")
        self.assertEqual(get_root_domain("example.com"), ".example.com")

if __name__ == "__main__":
    unittest.main()
