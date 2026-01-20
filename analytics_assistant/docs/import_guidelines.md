# Python 导入规范

## 导入原则

为了保持代码的一致性和可维护性，项目统一使用以下导入规范：

---

## 1. 源代码中的导入（`src/` 目录下）

### ✅ 使用相对导入（推荐）

**PEP 8 说明**：
- PEP 8 推荐使用**绝对导入**（更可读）
- 但**相对导入是可接受的替代方案**，特别是在复杂包结构中
- 现代 Python 项目（Django、Flask、LangChain）普遍使用相对导入

**我们选择相对导入的原因**：
- 更简洁（不需要完整包名 `analytics_assistant.src.infra.rag`）
- 不依赖 Python 路径配置
- 明确表示模块之间的层级关系
- 更易于重构和移动模块
- 包名变化时不需要全局修改

### 示例

#### 同级模块导入
```python
# analytics_assistant/src/infra/rag/retriever.py
from .models import FieldChunk, RetrievalResult
from .vector_index_manager import VectorIndexManager
from .reranker import BaseReranker
```

#### 上级模块导入
```python
# analytics_assistant/src/infra/rag/vector_index_manager.py
from ...ai import get_embeddings  # 上三级到 src/infra/ai
```

#### 跨层级导入
```python
# analytics_assistant/src/agents/base/node.py
from ...infra.ai import get_model_manager, TaskType  # 从 agents 到 infra
```

---

## 2. 测试文件中的导入（`tests/` 目录下）

### ✅ 使用绝对导入

**原因**：
- 测试文件不在包内，相对导入不适用
- 绝对导入更清晰地表示被测试的模块
- 便于理解测试的目标

### 示例

```python
# analytics_assistant/tests/infra/rag/test_models.py
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 使用绝对导入
from src.infra.rag.models import (
    RetrievalSource,
    EmbeddingResult,
    FieldChunk,
    RetrievalResult,
)
```

---

## 3. 延迟导入（避免循环依赖）

### ✅ 在函数/方法内部导入

**使用场景**：
- 避免模块级别的循环依赖
- 减少启动时间（可选依赖）

### 示例

```python
# analytics_assistant/src/infra/rag/vector_index_manager.py
def _create_default_embedding_provider(self) -> Optional[Any]:
    """延迟导入，避免循环依赖"""
    try:
        # 优先使用相对导入
        from ...ai import get_embeddings
    except ImportError:
        # 回退到绝对导入（用于特殊环境）
        from src.infra.ai import get_embeddings
    
    return get_embeddings()
```

---

## 4. 标准库和第三方库导入

### ✅ 使用绝对导入

```python
# 标准库
import os
import sys
from pathlib import Path
from typing import List, Optional

# 第三方库
import numpy as np
import faiss
from langchain.embeddings import OpenAIEmbeddings
```

---

## 5. 导入顺序（PEP 8）

### ✅ 按以下顺序组织导入

1. **标准库导入**
2. **第三方库导入**
3. **本地应用/库导入**

每组之间用空行分隔。

### 示例

```python
# 1. 标准库
import os
import sys
from pathlib import Path
from typing import List, Optional

# 2. 第三方库
import numpy as np
import faiss
from langchain.embeddings import OpenAIEmbeddings

# 3. 本地导入（相对导入）
from .models import FieldChunk, RetrievalResult
from .vector_index_manager import VectorIndexManager
```

---

## 6. 避免的导入方式

### ❌ 不要使用通配符导入
```python
# 错误
from .models import *

# 正确
from .models import FieldChunk, RetrievalResult
```

### ❌ 不要在源代码中混用绝对导入和相对导入
```python
# 错误（混用）
from src.infra.rag.models import FieldChunk  # 绝对导入
from .vector_index_manager import VectorIndexManager  # 相对导入

# 正确（统一使用相对导入）
from .models import FieldChunk
from .vector_index_manager import VectorIndexManager
```

### ❌ 不要使用 `analytics_assistant.src` 前缀
```python
# 错误
from analytics_assistant.src.infra.ai import get_embeddings

# 正确（相对导入）
from ...ai import get_embeddings

# 或（测试中的绝对导入）
from src.infra.ai import get_embeddings
```

---

## 7. 特殊情况处理

### 循环依赖

**重要原则：循环依赖必须找到根本原因并解决，不能用延迟导入掩盖问题！**

如果遇到循环依赖，按以下顺序处理：

1. **重构代码结构**（最佳方案，必须优先考虑）
   - 分析依赖关系，找出循环的根源
   - 将共享的类型/接口提取到独立模块
   - 调整模块职责，消除不必要的依赖
   - 使用依赖注入而不是直接导入

2. **使用类型注解的字符串形式**（仅用于类型检查）
   ```python
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from .other_module import SomeClass
   
   def my_function(obj: "SomeClass") -> None:
       # 运行时不会导入，只用于类型检查
       pass
   ```

3. **❌ 不要使用延迟导入**（在函数内导入）
   - 延迟导入只是掩盖问题，不是解决方案
   - 会导致代码难以理解和维护
   - 可能引入运行时错误
   
   ```python
   # ❌ 错误示例：使用延迟导入
   def my_function():
       from ...other_module import something  # 不好的做法
       return something()
   
   # ✅ 正确做法：重构代码结构，消除循环依赖
   ```

### 真实案例：RAG 和 AI 模块

**问题**：`infra/rag/vector_index_manager.py` 需要使用 `infra/ai/get_embeddings()`

**错误做法**（延迟导入）：
```python
def _create_default_embedding_provider(self):
    try:
        from ...ai import get_embeddings  # 延迟导入
    except ImportError:
        from src.infra.ai import get_embeddings  # 回退
    return get_embeddings()
```

**正确做法**（直接使用相对导入）：
```python
# 在文件顶部或函数内直接导入（如果确实不存在循环依赖）
from ...ai import get_embeddings

def _create_default_embedding_provider(self):
    return get_embeddings()
```

**分析**：
- AI 模块不依赖 RAG 模块，所以不存在真正的循环依赖
- 使用延迟导入是不必要的，反而增加了复杂度
- 直接使用相对导入是正确的做法

---

## 8. 导入检查清单

在提交代码前，检查：

- [ ] 源代码中使用相对导入
- [ ] 测试文件中使用绝对导入
- [ ] 导入按标准库、第三方库、本地导入分组
- [ ] 每组之间有空行分隔
- [ ] 没有使用通配符导入
- [ ] 没有未使用的导入
- [ ] 循环依赖已解决（使用延迟导入或重构）

---

## 9. IDE 配置建议

### VS Code
在 `.vscode/settings.json` 中配置：
```json
{
  "python.analysis.extraPaths": ["${workspaceFolder}"],
  "python.linting.pylintArgs": [
    "--init-hook",
    "import sys; sys.path.append('${workspaceFolder}')"
  ]
}
```

### PyCharm
1. 右键项目根目录 → Mark Directory as → Sources Root
2. Settings → Project → Project Structure → 添加 `analytics_assistant` 为 Sources

---

## 10. 常见问题

### Q: 为什么测试文件不使用相对导入？
A: 测试文件不在包内（`tests/` 和 `src/` 是分离的），相对导入会失败。

### Q: 什么时候使用延迟导入？
A: 只在遇到循环依赖或需要可选依赖时使用。

### Q: 如何处理 `ModuleNotFoundError`？
A: 
1. 检查 Python 路径是否正确
2. 确认使用了正确的导入方式（源代码用相对导入，测试用绝对导入）
3. 检查 `__init__.py` 文件是否存在

---

## 总结

**PEP 8 的立场：**
- 推荐绝对导入（更可读）
- 相对导入是可接受的替代方案（特别是复杂包结构）

**我们的选择：相对导入**

原因：
1. 更简洁（不需要 `analytics_assistant.src.infra.rag` 这样的长路径）
2. 不依赖 Python 路径配置
3. 符合现代 Python 项目实践（Django、Flask、LangChain）
4. 更易于重构

| 场景 | 导入方式 | 示例 |
|------|---------|------|
| 源代码（同级） | 相对导入 | `from .models import FieldChunk` |
| 源代码（上级） | 相对导入 | `from ...ai import get_embeddings` |
| 测试文件 | 绝对导入 | `from src.infra.rag.models import FieldChunk` |
| 标准库/第三方库 | 绝对导入 | `import numpy as np` |

**注意**：如果你更喜欢绝对导入，也完全可以，只需统一使用即可：
```python
# 绝对导入方式（也是有效的）
from analytics_assistant.src.infra.rag.models import FieldChunk
from analytics_assistant.src.infra.ai import get_embeddings
```

但我们选择相对导入是因为它更简洁、更实用。
