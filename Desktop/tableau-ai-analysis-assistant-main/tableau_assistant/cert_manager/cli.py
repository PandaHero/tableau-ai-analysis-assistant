"""
证书管理器命令行工具

提供命令行接口来管理SSL证书
"""
import sys
import argparse
import logging
from pathlib import Path

from .manager import CertificateManager
from .config import get_ssl_config


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_fetch(args):
    """获取证书命令"""
    manager = CertificateManager(cert_dir=args.cert_dir)
    
    if args.hostname == "deepseek":
        print("正在获取DeepSeek证书...")
        result = manager.fetch_deepseek_certificates(force=args.force)
        print(f"\n✓ 证书已保存:")
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
    
    elif args.hostname == "tableau":
        print("正在获取Tableau Server证书...")
        tableau_domain = args.tableau_domain
        if not tableau_domain:
            import os
            tableau_domain = os.getenv("TABLEAU_DOMAIN")
            if not tableau_domain:
                print("✗ 错误: 请使用 --tableau-domain 指定Tableau服务器地址")
                print("   或设置环境变量 TABLEAU_DOMAIN")
                sys.exit(1)
        
        result = manager.fetch_tableau_certificates(
            tableau_domain=tableau_domain,
            force=args.force
        )
        print(f"\n✓ 证书已保存:")
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
    
    else:
        print(f"正在获取 {args.hostname}:{args.port} 的证书...")
        result = manager.fetch_certificate(
            args.hostname,
            args.port,
            args.output
        )
        print(f"\n✓ 证书已保存: {result['cert_file']}")


def cmd_validate(args):
    """验证证书命令"""
    manager = CertificateManager(cert_dir=args.cert_dir)
    
    if args.connection:
        # 验证连接
        print(f"正在验证连接: {args.connection}...")
        hostname, port = args.connection.split(':') if ':' in args.connection else (args.connection, 443)
        result = manager.validate_connection(hostname, int(port), args.cert_file)
        
        if result["success"]:
            print("\n✓ 连接验证成功")
            print(f"  协议: {result['protocol']}")
            print(f"  加密套件: {result['cipher']}")
            print(f"  证书主题: {result['cert_info'].get('subject', {}).get('commonName', 'N/A')}")
        else:
            print("\n✗ 连接验证失败")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)
    
    elif args.chain:
        # 验证证书链
        cert_file = args.cert_file or (Path(args.cert_dir) / "deepseek_full_chain.pem")
        print(f"正在验证证书链: {cert_file}...")
        result = manager.validate_certificate_chain(str(cert_file))
        
        if result["valid"]:
            print(f"\n✓ 证书链验证成功 (包含{result['cert_count']}个证书)")
            for cert in result["certificates"]:
                print(f"\n  证书 {cert['index']}:")
                print(f"    主题: {cert['subject_cn']}")
                print(f"    颁发者: {cert['issuer_cn']}")
                print(f"    有效期: {cert['not_before']} 至 {cert['not_after']}")
        else:
            print("\n✗ 证书链验证失败")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)
    
    else:
        # 验证证书文件
        cert_file = args.cert_file or (Path(args.cert_dir) / "deepseek_full_chain.pem")
        print(f"正在验证证书: {cert_file}...")
        result = manager.validate_certificate(str(cert_file))
        
        if result["valid"]:
            print(f"\n✓ 证书验证成功 (包含{result['cert_count']}个证书)")
            
            if result.get("days_remaining") is not None:
                days = result["days_remaining"]
                if days < 0:
                    print(f"  ⚠️  证书已过期 {abs(days)} 天")
                elif days < 30:
                    print(f"  ⚠️  证书将在 {days} 天后过期")
                else:
                    print(f"  ✓ 证书有效期剩余 {days} 天")
        else:
            print("\n✗ 证书验证失败")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)


def cmd_status(args):
    """查看状态命令"""
    manager = CertificateManager(cert_dir=args.cert_dir)
    status = manager.get_status()
    
    print("="*60)
    print("证书管理器状态")
    print("="*60)
    
    print(f"\n证书目录: {status['cert_dir']}")
    
    print(f"\nSSL配置:")
    ssl_config = status['ssl_config']
    print(f"  验证: {'启用' if ssl_config['is_enabled'] else '禁用'}")
    print(f"  证书来源: {ssl_config['cert_source']}")
    if ssl_config['ca_bundle']:
        print(f"  证书文件: {ssl_config['ca_bundle']}")
    
    print(f"\n证书文件:")
    for cert_file, info in status['certificates'].items():
        if info['exists']:
            status_icon = "✓" if info['valid'] else "✗"
            print(f"  {status_icon} {cert_file}")
            if info.get('cert_count'):
                print(f"      包含 {info['cert_count']} 个证书")
            if info.get('errors'):
                for error in info['errors']:
                    print(f"      错误: {error}")
            if info.get('warnings'):
                for warning in info['warnings']:
                    print(f"      警告: {warning}")
        else:
            print(f"  - {cert_file} (不存在)")


def cmd_config(args):
    """查看配置命令"""
    ssl_config = get_ssl_config()
    
    print("="*60)
    print("SSL配置")
    print("="*60)
    
    print(f"\n{ssl_config}")
    print(f"\n详细信息:")
    for key, value in ssl_config.to_dict().items():
        print(f"  {key}: {value}")
    
    print(f"\n使用示例:")
    print(f"\n  # requests库")
    print(f"  import requests")
    print(f"  response = requests.get(url, **ssl_config.requests_kwargs())")
    
    print(f"\n  # httpx库")
    print(f"  import httpx")
    print(f"  client = httpx.Client(**ssl_config.httpx_client_kwargs())")
    
    print(f"\n  # aiohttp库")
    print(f"  import aiohttp")
    print(f"  async with aiohttp.ClientSession() as session:")
    print(f"      async with session.get(url, **ssl_config.aiohttp_kwargs()) as response:")
    print(f"          ...")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="证书管理器 - 管理SSL/TLS证书",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 获取DeepSeek证书
  python -m cert_manager.cli fetch deepseek
  
  # 获取Tableau Server证书
  python -m cert_manager.cli fetch tableau --tableau-domain https://tableau.company.com
  
  # 获取指定服务器证书
  python -m cert_manager.cli fetch api.example.com
  
  # 验证证书文件
  python -m cert_manager.cli validate
  
  # 验证SSL连接
  python -m cert_manager.cli validate --connection api.deepseek.com
  
  # 验证证书链
  python -m cert_manager.cli validate --chain
  
  # 查看状态
  python -m cert_manager.cli status
  
  # 查看配置
  python -m cert_manager.cli config
        """
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    parser.add_argument(
        '--cert-dir',
        default=None,
        help='证书目录 (默认: tableau_assistant/certs)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # fetch命令
    fetch_parser = subparsers.add_parser('fetch', help='获取证书')
    fetch_parser.add_argument(
        'hostname',
        help='主机名 (使用 "deepseek" 获取DeepSeek证书, "tableau" 获取Tableau证书)'
    )
    fetch_parser.add_argument(
        '--port',
        type=int,
        default=443,
        help='端口号 (默认: 443)'
    )
    fetch_parser.add_argument(
        '--output',
        help='输出文件路径'
    )
    fetch_parser.add_argument(
        '--tableau-domain',
        help='Tableau服务器域名 (例如: https://tableau.company.com)'
    )
    fetch_parser.add_argument(
        '--force',
        action='store_true',
        help='强制重新获取'
    )
    fetch_parser.set_defaults(func=cmd_fetch)
    
    # validate命令
    validate_parser = subparsers.add_parser('validate', help='验证证书')
    validate_parser.add_argument(
        '--cert-file',
        help='证书文件路径'
    )
    validate_parser.add_argument(
        '--connection',
        help='验证SSL连接 (格式: hostname[:port])'
    )
    validate_parser.add_argument(
        '--chain',
        action='store_true',
        help='验证证书链'
    )
    validate_parser.set_defaults(func=cmd_validate)
    
    # status命令
    status_parser = subparsers.add_parser('status', help='查看状态')
    status_parser.set_defaults(func=cmd_status)
    
    # config命令
    config_parser = subparsers.add_parser('config', help='查看配置')
    config_parser.set_defaults(func=cmd_config)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    setup_logging(args.verbose)
    
    try:
        args.func(args)
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
