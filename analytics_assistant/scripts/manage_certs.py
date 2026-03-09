#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SSL 证书管理工具

功能：
1. 查看证书信息
2. 验证证书有效性
3. 生成自签名证书
4. 切换证书配置
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.ssl_manager import get_ssl_manager


def print_header(message: str):
    """打印标题"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}\n")


def print_success(message: str):
    """打印成功消息"""
    print(f"[SUCCESS] {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"[ERROR] {message}")


def print_info(message: str):
    """打印信息"""
    print(f"[INFO] {message}")


def cmd_info(args):
    """查看证书信息"""
    print_header("证书信息")
    
    try:
        config = get_config()
        ssl_manager = get_ssl_manager(config)
        
        cert_file, key_file = ssl_manager.get_cert_paths()
        print_info(f"证书文件: {cert_file}")
        print_info(f"密钥文件: {key_file}")
        print_info(f"热更新间隔: {ssl_manager.reload_interval}秒")
        
        print("\n证书详情:")
        cert_info = ssl_manager.get_cert_info()
        
        if cert_info:
            print(f"  主题: {cert_info.get('subject')}")
            print(f"  颁发者: {cert_info.get('issuer')}")
            print(f"  有效期开始: {cert_info.get('not_valid_before')}")
            print(f"  有效期结束: {cert_info.get('not_valid_after')}")
            print(f"  序列号: {cert_info.get('serial_number')}")
            
            if cert_info.get('is_expired'):
                print_error("  状态: 已过期")
            else:
                print_success("  状态: 有效")
        else:
            print_error("无法读取证书信息")
            
    except Exception as e:
        print_error(f"获取证书信息失败: {e}")
        sys.exit(1)


def cmd_validate(args):
    """验证证书有效性"""
    print_header("验证证书")
    
    try:
        config = get_config()
        ssl_manager = get_ssl_manager(config)
        
        if ssl_manager.validate_certificate():
            print_success("证书有效")
        else:
            print_error("证书无效或已过期")
            sys.exit(1)
            
    except Exception as e:
        print_error(f"验证证书失败: {e}")
        sys.exit(1)


def cmd_list(args):
    """列出所有证书配置"""
    print_header("证书配置列表")
    
    try:
        config = get_config()
        ssl_config = config.get('ssl', {})
        certificates = ssl_config.get('certificates', {})
        active_cert = ssl_config.get('active_cert', 'localhost')
        
        for name, cert_config in certificates.items():
            is_active = " (当前使用)" if name == active_cert else ""
            print(f"\n{name}{is_active}:")
            print(f"  证书文件: {cert_config.get('cert_file')}")
            print(f"  密钥文件: {cert_config.get('key_file')}")
            print(f"  热更新间隔: {cert_config.get('reload_interval', 0)}秒")
            
    except Exception as e:
        print_error(f"列出证书配置失败: {e}")
        sys.exit(1)


def cmd_generate(args):
    """生成自签名证书"""
    print_header("生成自签名证书")
    
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        from datetime import datetime, timedelta
        
        # 生成私钥
        print_info("生成私钥...")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # 生成证书
        print_info("生成证书...")
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, args.country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, args.state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, args.city),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, args.org),
            x509.NameAttribute(NameOID.COMMON_NAME, args.common_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=args.days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(args.common_name),
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256(), default_backend())
        
        # 保存证书
        cert_file = Path(args.output_dir) / f"{args.name}.crt"
        key_file = Path(args.output_dir) / f"{args.name}.key"
        
        cert_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        with open(key_file, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        print_success(f"证书已生成:")
        print_info(f"  证书文件: {cert_file}")
        print_info(f"  密钥文件: {key_file}")
        print_info(f"  有效期: {args.days} 天")
        
    except ImportError:
        print_error("需要安装 cryptography 库: pip install cryptography")
        sys.exit(1)
    except Exception as e:
        print_error(f"生成证书失败: {e}")
        sys.exit(1)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='SSL 证书管理工具')
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # info 命令
    parser_info = subparsers.add_parser('info', help='查看证书信息')
    parser_info.set_defaults(func=cmd_info)
    
    # validate 命令
    parser_validate = subparsers.add_parser('validate', help='验证证书有效性')
    parser_validate.set_defaults(func=cmd_validate)
    
    # list 命令
    parser_list = subparsers.add_parser('list', help='列出所有证书配置')
    parser_list.set_defaults(func=cmd_list)
    
    # generate 命令
    parser_generate = subparsers.add_parser('generate', help='生成自签名证书')
    parser_generate.add_argument('--name', default='localhost', help='证书名称')
    parser_generate.add_argument('--common-name', default='localhost', help='Common Name')
    parser_generate.add_argument('--country', default='CN', help='国家代码')
    parser_generate.add_argument('--state', default='Beijing', help='省份')
    parser_generate.add_argument('--city', default='Beijing', help='城市')
    parser_generate.add_argument('--org', default='Analytics Assistant', help='组织名称')
    parser_generate.add_argument('--days', type=int, default=3650, help='有效期（天）')
    parser_generate.add_argument(
        '--output-dir',
        default='analytics_assistant/data/certs',
        help='输出目录'
    )
    parser_generate.set_defaults(func=cmd_generate)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    # 需要导入 ipaddress 用于生成证书
    import ipaddress
    main()
