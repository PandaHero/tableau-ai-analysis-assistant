# 已知问题

## Windows SQLite 文件锁问题

### 问题描述

在 Windows 平台上运行 SQLite 存储后端的单元测试时，会出现文件锁无法释放的问题：

```
PermissionError: [WinError 32] 另一个程序正在使用此文件，进程无法访问。
```

### 根本原因

1. **LangGraph SqliteStore 内部引用**：LangGraph 的 SqliteStore 可能在内部持有额外的连接引用
2. **Windows 文件锁机制**：Windows 的文件锁释放比 Linux/Mac 更严格，即使调用 `conn.close()` 后，文件锁也可能不会立即释放
3. **Python 垃圾回收延迟**：Python 的垃圾回收器可能不会立即回收已关闭的连接对象

### 影响范围

- **仅影响测试**：生产环境不受影响，因为数据库文件不会被频繁删除
- **仅影响 Windows**：Linux 和 Mac 平台不受影响
- **仅影响 SQLite**：Redis 和 Memory 后端不受影响

### 解决方案

#### 方案 1：使用持久化测试目录（推荐）

不使用 `tempfile.TemporaryDirectory()`，而是使用固定的测试目录：

```python
import pytest
from pathlib import Path

@pytest.fixture
def test_db_path(tmp_path):
    """提供测试数据库路径"""
    return tmp_path / "test.db"

def test_basic_operations(test_db_path):
    config = StoreConfig(
        backend="sqlite",
        namespace="test",
        connection_string=str(test_db_path)
    )
    
    with StorageFactory.create_store(config) as store:
        # 测试代码
        pass
    
    # pytest 会在测试结束后自动清理 tmp_path
```

#### 方案 2：添加延迟（不推荐）

在关闭连接后添加短暂延迟：

```python
import time
import gc

store.close()
gc.collect()
time.sleep(0.1)  # 等待文件锁释放
```

#### 方案 3：忽略清理错误（临时方案）

使用 `TemporaryDirectory` 的 `ignore_cleanup_errors` 参数：

```python
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
    # 测试代码
    pass
```

### 当前状态

- ✅ **Memory 后端测试**：全部通过（3/3）
- ⚠️ **SQLite 后端测试**：Windows 文件锁问题（7/7 失败）
- ⏳ **Redis 后端测试**：待测试

### 后续计划

1. 联系 LangGraph 团队，报告 Windows 文件锁问题
2. 考虑使用 pytest 的 `tmp_path` fixture 替代 `TemporaryDirectory`
3. 在 CI/CD 中使用 Linux 环境运行测试

### 参考资料

- [SQLite on Windows: File Locking](https://www.sqlite.org/lockingv3.html)
- [Python tempfile module](https://docs.python.org/3/library/tempfile.html)
- [LangGraph Store Documentation](https://langchain-ai.github.io/langgraph/reference/store/)

