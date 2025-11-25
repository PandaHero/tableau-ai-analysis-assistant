"""
Certificate Manager 使用示例
"""
import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)


def example_basic():
    """基础使用示例"""
    print("="*60)
    print("示例1: 基础使用")
    print("="*60 + "\n")
    
    from cert_manager import CertificateManager
    
    # 初始化
    manager = CertificateManager(cert_dir="certs")
    
    # 获取DeepSeek证书
    print("1. 获取DeepSeek证书...")
    result = manager.fetch_deepseek_certificates()
    print(f"   ✓ 证书已保存: {result['full_chain']}\n")
    
    # 验证证书
    print("2. 验证证书...")
    validation = manager.validate_certificate()
    print(f"   ✓ 证书有效: {validation['valid']}")
    print(f"   ✓ 包含证书数: {validation['cert_count']}\n")
    
    # 查看状态
    print("3. 查看状态...")
    status = manager.get_status()
    print(f"   ✓ 证书目录: {status['cert_dir']}")
    print(f"   ✓ SSL验证: {'启用' if status['ssl_config']['is_enabled'] else '禁用'}\n")


def example_requests():
    """使用requests库的示例"""
    print("="*60)
    print("示例2: 使用requests库")
    print("="*60 + "\n")
    
    from cert_manager import get_ssl_config
    import requests
    
    # 获取SSL配置
    ssl_config = get_ssl_config()
    print(f"SSL配置: {ssl_config}\n")
    
    # 发送请求
    print("发送HTTPS请求...")
    try:
        response = requests.get(
            "https://api.deepseek.com",
            **ssl_config.requests_kwargs(),
            timeout=10
        )
        print(f"✓ 请求成功! 状态码: {response.status_code}\n")
    except Exception as e:
        print(f"✗ 请求失败: {e}\n")


def example_httpx():
    """使用httpx库的示例"""
    print("="*60)
    print("示例3: 使用httpx库")
    print("="*60 + "\n")
    
    from cert_manager import get_ssl_config
    import httpx
    
    # 获取SSL配置
    ssl_config = get_ssl_config()
    
    # 创建客户端
    print("创建httpx客户端...")
    client = httpx.Client(**ssl_config.httpx_client_kwargs())
    
    # 发送请求
    print("发送HTTPS请求...")
    try:
        response = client.get("https://api.deepseek.com", timeout=10)
        print(f"✓ 请求成功! 状态码: {response.status_code}\n")
    except Exception as e:
        print(f"✗ 请求失败: {e}\n")
    finally:
        client.close()


async def example_aiohttp():
    """使用aiohttp库的示例"""
    print("="*60)
    print("示例4: 使用aiohttp库")
    print("="*60 + "\n")
    
    from cert_manager import get_ssl_config
    import aiohttp
    
    # 获取SSL配置
    ssl_config = get_ssl_config()
    
    # 发送异步请求
    print("发送异步HTTPS请求...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.deepseek.com",
                **ssl_config.aiohttp_kwargs(),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                print(f"✓ 请求成功! 状态码: {response.status}\n")
    except Exception as e:
        print(f"✗ 请求失败: {e}\n")


def example_validation():
    """证书验证示例"""
    print("="*60)
    print("示例5: 证书验证")
    print("="*60 + "\n")
    
    from cert_manager import CertificateManager
    
    manager = CertificateManager()
    
    # 验证证书文件
    print("1. 验证证书文件...")
    result = manager.validate_certificate()
    if result["valid"]:
        print(f"   ✓ 证书有效")
        if result.get("days_remaining"):
            print(f"   ✓ 剩余有效期: {result['days_remaining']} 天")
    else:
        print(f"   ✗ 证书无效: {result['errors']}")
    print()
    
    # 验证SSL连接
    print("2. 验证SSL连接...")
    result = manager.validate_connection("api.deepseek.com")
    if result["success"]:
        print(f"   ✓ 连接成功")
        print(f"   ✓ 协议: {result['protocol']}")
        print(f"   ✓ 加密套件: {result['cipher']}")
    else:
        print(f"   ✗ 连接失败: {result['errors']}")
    print()
    
    # 验证证书链
    print("3. 验证证书链...")
    result = manager.validate_certificate_chain()
    if result["valid"]:
        print(f"   ✓ 证书链有效 (包含{result['cert_count']}个证书)")
        for cert in result["certificates"]:
            print(f"   - 证书{cert['index']}: {cert['subject_cn']}")
    else:
        print(f"   ✗ 证书链无效: {result['errors']}")
    print()


def example_custom_cert():
    """自定义证书示例"""
    print("="*60)
    print("示例6: 使用自定义证书")
    print("="*60 + "\n")
    
    from cert_manager import CertificateManager
    
    # 使用自定义证书路径
    manager = CertificateManager(
        cert_dir="custom_certs",
        ca_bundle="custom_certs/my_cert.pem"
    )
    
    ssl_config = manager.get_ssl_config()
    print(f"SSL配置: {ssl_config}")
    print(f"证书来源: {ssl_config.cert_source}\n")


def example_fetch_custom():
    """获取自定义服务器证书示例"""
    print("="*60)
    print("示例7: 获取自定义服务器证书")
    print("="*60 + "\n")
    
    from cert_manager import CertificateManager
    
    manager = CertificateManager()
    
    # 获取指定服务器的证书
    print("获取 www.google.com 的证书...")
    try:
        result = manager.fetch_certificate("www.google.com", 443)
        print(f"✓ 证书已保存: {result['cert_file']}")
        print(f"  主题: {result['cert_info'].get('subject')}\n")
    except Exception as e:
        print(f"✗ 获取失败: {e}\n")


def example_production():
    """生产环境使用示例"""
    print("="*60)
    print("示例8: 生产环境配置")
    print("="*60 + "\n")
    
    import os
    from cert_manager import CertificateManager
    
    # 模拟生产环境配置
    os.environ["LLM_VERIFY_SSL"] = "true"
    os.environ["LLM_CA_BUNDLE"] = "certs/deepseek_full_chain.pem"
    
    # 初始化
    manager = CertificateManager()
    
    # 检查证书状态
    print("1. 检查证书状态...")
    status = manager.get_status()
    
    ssl_config = status['ssl_config']
    print(f"   SSL验证: {'启用' if ssl_config['is_enabled'] else '禁用'}")
    print(f"   证书来源: {ssl_config['cert_source']}")
    
    # 验证证书
    print("\n2. 验证证书...")
    result = manager.validate_certificate()
    
    if not result["valid"]:
        print("   ⚠️  证书无效,尝试重新获取...")
        manager.fetch_deepseek_certificates(force=True)
        print("   ✓ 证书已更新")
    else:
        print("   ✓ 证书有效")
        
        # 检查过期时间
        if result.get("expiring_soon"):
            print(f"   ⚠️  证书即将过期 (剩余{result['days_remaining']}天)")
            print("   建议更新证书")
        elif result.get("days_remaining"):
            print(f"   ✓ 证书有效期剩余 {result['days_remaining']} 天")
    
    print()


def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("Certificate Manager 使用示例")
    print("="*60 + "\n")
    
    try:
        # 基础示例
        example_basic()
        
        # HTTP客户端示例
        example_requests()
        example_httpx()
        asyncio.run(example_aiohttp())
        
        # 验证示例
        example_validation()
        
        # 自定义配置示例
        example_custom_cert()
        example_fetch_custom()
        
        # 生产环境示例
        example_production()
        
        print("="*60)
        print("所有示例运行完成!")
        print("="*60 + "\n")
    
    except Exception as e:
        print(f"\n✗ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
