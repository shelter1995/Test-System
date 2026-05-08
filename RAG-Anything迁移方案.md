# RAG-Anything 迁移实施方案

## 一、项目背景

### 1.1 现有架构

```
ai-tutor-system (端口 8002)
    │
    ├── HTTP POST ──→ rag-anything-api /ai_enhanced_search  (知识检索)
    ├── HTTP POST ──→ rag-anything-api /search              (备用检索)
    │
    └── HTTP POST ──→ MiniMax API  (AI对话生成)
```

- **rag-anything-api**: 基于 LightRAG + Sentence Transformers 的纯向量检索系统
- **ai-tutor-system**: AI话术陪练系统，通过 REST API 调用 rag-anything-api
- **调用接口**: `POST /ai_enhanced_search`、`POST /search`、`GET /status`

### 1.2 迁移目标

将 rag-anything-api 的检索引擎替换为 RAG-Anything（基于 LightRAG 的知识图谱+向量混合检索），提升知识检索的准确性和关联性。

### 1.3 用户可用的 AI 服务

| 服务 | 类型 | OpenAI 兼容 |
|------|------|-------------|
| MiniMax | LLM | 是（chatcompletion_v2） |
| DeepSeek | LLM | 是（/v1/chat/completions） |
| 硅基流动 | LLM + Embedding | 是（/v1/chat/completions、/v1/embeddings） |
| Kimi (Moonshot) | LLM | 是（/v1/chat/completions） |

---

## 二、可行性分析

### 2.1 ✅ 可行的部分

| 维度 | 分析 |
|------|------|
| **LLM 对接** | RAG-Anything 通过函数式接口自定义 LLM，DeepSeek/硅基流动/Kimi 都提供 OpenAI 兼容 API，可直接对接 |
| **Embedding** | 硅基流动提供 BAAI/bge-m3 Embedding API，与 LightRAG 推荐一致 |
| **存储后端** | LightRAG 支持内置 JSON KV Store（零配置），也支持 PostgreSQL/Neo4j 等 |
| **API 兼容** | 可编写 FastAPI 适配层，暴露与现有 rag-anything-api 相同的 REST 接口 |

### 2.2 ⚠️ 需要注意的风险

| 风险 | 等级 | 说明 |
|------|------|------|
| **LLM 质量要求** | 中 | LightRAG 推荐 32B+ 参数模型、32KB+ 上下文。MiniMax-M2.7 应满足，但小模型效果可能不佳 |
| **知识库重建** | 中 | 无法直接迁移 LightRAG 数据，所有文档需重新索引 |
| **依赖复杂度** | 中 | 需要安装 MinerU（文档解析）、LibreOffice（Office文档） |
| **API 延迟** | 低 | 知识图谱构建需要多次 LLM 调用，索引阶段较慢 |
| **Embedding 绑定** | 低 | 一旦确定 Embedding 模型，后续不可更改（需删除重建） |

### 2.3 ❌ 不兼容的部分

| 项目 | 说明 |
|------|------|
| **数据库架构** | 现有多数据库隔离架构（business_video_ringtone、ccs_gyl 等）需要重新设计 |
| **图片/音频/视频处理器** | RAG-Anything 的文档解析依赖 MinerU，现有的自研处理器需要适配或保留 |
| **MCP 协议** | 现有的 `/mcp` 端点需要重新实现 |

---

## 三、架构设计

### 3.1 目标架构

```
ai-tutor-system (端口 8002)  [不变]
    │
    ├── HTTP POST ──→ rag-anything-api /ai_enhanced_search  [接口不变]
    ├── HTTP POST ──→ rag-anything-api /search              [接口不变]
    │
    └── HTTP POST ──→ MiniMax API  [不变]

rag-anything-api (端口 8003)  [唯一知识库入口]
    │
    ├── RAG-Anything 核心引擎
    │   ├── LightRAG (知识图谱 + 向量检索)
    │   ├── MinerU (文档解析)
    │   └── 自定义 LLM/Embedding 函数
    │
    ├── 国产 AI 适配层
    │   ├── DeepSeek LLM (主推理)
    │   ├── 硅基流动 Embedding (bge-m3)
    │   └── MiniMax LLM (备选)
    │
    └── REST API 适配层 (兼容现有接口)
```

### 3.2 多数据库方案

现有系统有 4 个隔离的数据库，RAG-Anything 默认是单实例。方案：

**方案 A（推荐）：单实例 + 标签过滤**
- 使用一个 RAG-Anything 实例
- 文档入库时在 metadata 中标记 `database_id`
- 查询时通过 metadata 过滤
- 优点：简单，共享知识图谱
- 缺点：数据库间没有完全隔离

**方案 B：多实例**
- 每个数据库创建独立的 RAG-Anything 实例
- 优点：完全隔离
- 缺点：资源占用大，知识图谱不互通

**建议采用方案 A**，因为现有系统中各数据库的知识有一定关联性（都是销售培训相关）。

---

## 四、实施步骤

### 阶段一：环境准备（预计 1-2 天）

#### 4.1.1 安装依赖

```bash
# 1. 克隆 RAG-Anything
cd D:\GitHub_WorkSpace\Test-System
git clone https://github.com/HKUDS/RAG-Anything.git

# 2. 安装 RAG-Anything
cd RAG-Anything
pip install 'raganything[all]'

# 3. 安装 LibreOffice（Windows）
# 从 https://www.libreoffice.org/ 下载安装

# 4. 验证 MinerU
mineru --version
```

#### 4.1.2 验证国产 API 可用性

编写测试脚本，验证以下 API：

```python
# test_apis.py - 验证各 API 是否正常工作

# 1. DeepSeek LLM (推荐用于知识图谱构建)
#    - 端点: https://api.deepseek.com/v1/chat/completions
#    - 模型: deepseek-chat
#    - 测试: 实体提取、关系推理

# 2. 硅基流动 Embedding
#    - 端点: https://api.siliconflow.cn/v1/embeddings
#    - 模型: BAAI/bge-m3
#    - 测试: 中文文本向量化

# 3. MiniMax LLM (备选)
#    - 端点: https://api.minimax.chat/v1/text/chatcompletion_v2
#    - 模型: MiniMax-M2.7
```

#### 4.1.3 选择最优模型组合

| 用途 | 推荐模型 | 备选模型 | 说明 |
|------|---------|---------|------|
| **知识图谱构建（索引）** | DeepSeek-Chat | MiniMax-M2.7 | 需要强推理能力，不推荐推理模型 |
| **查询生成** | DeepSeek-Chat | Kimi | 需要长上下文理解 |
| **Embedding** | 硅基流动 bge-m3 | 本地 Sentence Transformers | 推荐 API 版本，维度更高 |

---

### 阶段二：适配层开发（预计 2-3 天）

#### 4.2.1 创建国产 AI 适配模块

新建文件：`rag-anything-api/adapters.py`

```python
"""
国产 AI 服务适配层
将 DeepSeek/硅基流动/MiniMax 的 API 包装为 LightRAG 所需的函数接口
"""

import requests
from typing import List, Optional

# ============= DeepSeek LLM 适配 =============

def deepseek_llm_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: list = [],
    **kwargs
) -> str:
    """DeepSeek LLM 适配函数，兼容 LightRAG 接口"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        f"{base_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096)
        },
        timeout=kwargs.get("timeout", 120)
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# ============= 硅基流动 Embedding 适配 =============

def siliconflow_embedding_func(
    texts: List[str],
    model: str = "BAAI/bge-m3"
) -> List[List[float]]:
    """硅基流动 Embedding 适配函数，兼容 LightRAG 接口"""
    api_key = os.getenv("SILICONFLOW_API_KEY")
    base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn")

    response = requests.post(
        f"{base_url}/v1/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "input": texts
        },
        timeout=60
    )
    response.raise_for_status()
    data = response.json()
    return [item["embedding"] for item in data["data"]]


# ============= MiniMax LLM 适配（备选） =============

def minimax_llm_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: list = [],
    **kwargs
) -> str:
    """MiniMax LLM 适配函数"""
    api_key = os.getenv("MINIMAX_API_KEY")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "MiniMax-M2.7",
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096)
        },
        timeout=kwargs.get("timeout", 120)
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
```

#### 4.2.2 创建 RAG-Anything 服务

新建文件：`rag-anything-api/app.py`

```python
"""
RAG-Anything REST API 服务
兼容现有 rag-anything-api 的接口，底层使用 RAG-Anything 引擎
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
from raganything import RAGAnything
from adapters import deepseek_llm_func, siliconflow_embedding_func
import os

app = FastAPI(title="RAG-Anything API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 初始化 RAG-Anything 实例
rag = RAGAnything(
    llm_model_func=deepseek_llm_func,
    embedding_func=siliconflow_embedding_func,
    # 存储配置
    lightrag_kwargs={
        "storage_dir": "./storage/lightrag",
    }
)

# ============= 兼容现有接口的数据模型 =============

class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 10
    database: Optional[str] = None  # 保留字段，用于 metadata 过滤

# ============= 兼容接口实现 =============

@app.post("/ai_enhanced_search")
async def ai_enhanced_search(request: SearchRequest):
    """AI增强搜索 - 兼容现有接口"""
    try:
        # 使用 RAG-Anything 的 mix 模式检索
        result = await rag.aquery(
            query=request.query,
            mode="mix",
            system_prompt="提取与查询最相关的知识片段，返回详细内容"
        )

        # 转换为现有格式
        results = [{
            "text": result,
            "metadata": {"source": "rag-anything", "database": request.database},
            "score": 1.0
        }]

        return {
            "query": request.query,
            "database": request.database,
            "results": results,
            "total_found": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search(request: SearchRequest):
    """语义搜索 - 兼容现有接口"""
    try:
        result = await rag.aquery(
            query=request.query,
            mode="naive"  # 使用基础向量检索模式
        )

        results = [{
            "text": result,
            "metadata": {"source": "rag-anything"},
            "score": 1.0
        }]

        return {
            "query": request.query,
            "results": results,
            "total_found": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def status():
    """系统状态 - 兼容现有接口"""
    return {
        "status": "running",
        "message": "RAG-Anything 智能检索系统",
        "summary": {
            "total_databases": 1,
            "total_documents": "见 Lightrag 存储",
        },
        "config": {
            "llm": "DeepSeek-Chat",
            "embedding": "BAAI/bge-m3 (硅基流动)"
        }
    }
```

#### 4.2.3 创建配置文件

新建文件：`rag-anything-api/.env`

```env
# DeepSeek LLM (推荐用于索引和查询)
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 硅基流动 Embedding
SILICONFLOW_API_KEY=your_siliconflow_api_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn

# MiniMax (备选 LLM)
MINIMAX_API_KEY=your_minimax_api_key

# 服务配置
RAG_SERVICE_PORT=8003
```

---

### 阶段三：知识库迁移（预计 1-2 天）

#### 4.3.1 导出现有知识

编写脚本从 LightRAG 导出所有文档：

```python
# migrate_knowledge.py
# 1. 连接现有 LightRAG
# 2. 遍历所有数据库（business_video_ringtone, ccs_gyl, keyexams）
# 3. 导出文本内容 + metadata
# 4. 保存为 JSON 文件
```

#### 4.3.2 重新索引到 RAG-Anything

```python
# reindex.py
# 1. 加载导出的 JSON 文件
# 2. 按数据库分组
# 3. 调用 rag.process_document_complete() 逐个导入
# 4. 在 metadata 中标记 database_id
```

#### 4.3.3 验证检索质量

验证测试：
- 使用典型业务查询词
- 验证 RAG-Anything（知识图谱+向量）的返回结果
- 评估相关性和准确性

---

### 阶段四：集成测试（预计 1 天）

#### 4.4.1 接口兼容性测试

```bash
# 测试所有现有接口
curl -X POST http://localhost:8003/ai_enhanced_search \
  -H "Content-Type: application/json" \
  -d '{"query": "商务视频彩铃价格", "database": "business_video_ringtone"}'

curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query": "开场话术"}'

curl http://localhost:8003/status
```

#### 4.4.2 端到端测试

1. 启动 rag-anything-api（端口 8003）
2. 启动 ai-tutor-system（端口 8002）
3. 打开前端界面
4. 执行完整的陪练流程：选场景 → 对话 → 评估 → 报告
5. 验证知识检索是否正常工作

---

### 阶段五：清理与文档（预计 0.5 天）

- 备份旧的 rag-anything-api 目录
- 更新项目文档（README、部署说明、使用说明）
- 更新启动脚本

---

## 五、文件结构

迁移后的项目结构：

```
D:\GitHub_WorkSpace\Test-System\
├── rag-anything-api/              # [新建] RAG-Anything API 服务
│   ├── app.py                     # FastAPI 服务主文件
│   ├── adapters.py                # 国产 AI 适配层
│   ├── config.py                  # 配置文件
│   ├── .env                       # API 密钥
│   ├── requirements.txt           # 依赖
│   └── storage/                   # LightRAG 存储目录
│       └── lightrag/
│
├── RAG-Anything/                  # [克隆] RAG-Anything 源码
│
├── rag-anything-api/                      # [保留] 旧 RAG 系统（备份）
│
├── ai-tutor-system/               # [不变] AI陪练系统
│   ├── tutor_backend.py
│   ├── tutor_config.py
│   └── static/
│
└── RAG-Anything迁移方案.md         # 本文档
```

---

## 六、风险与回退方案

### 6.1 风险应对

| 风险 | 应对措施 |
|------|---------|
| LLM 效果不佳 | 切换到更强的模型（如 DeepSeek-V3），或调整 system prompt |
| 索引速度太慢 | 减少文档数量，或使用并发处理 |
| Embedding 效果差 | 切换回本地 Sentence Transformers（写适配函数） |
| API 延迟增加 | 添加缓存层，或优化查询模式 |
| 知识图谱构建失败 | 降级到 naive 模式（纯向量检索） |

### 6.2 回退方案

旧服务已删除，不再保留双服务回退路径。后续效果问题直接在 8003 的 RAG-Anything 服务内优化。

---

## 七、时间估算

| 阶段 | 预计时间 | 依赖 |
|------|---------|------|
| 阶段一：环境准备 | 1-2 天 | 无 |
| 阶段二：适配层开发 | 2-3 天 | 阶段一完成 |
| 阶段三：知识库迁移 | 1-2 天 | 阶段二完成 |
| 阶段四：集成测试 | 1 天 | 阶段三完成 |
| 阶段五：清理文档 | 0.5 天 | 阶段四通过 |
| **总计** | **5.5-8.5 天** | |

---

## 八、决策点

在继续之前，需要确认以下事项：

1. **LLM 选择**：用 DeepSeek 还是 MiniMax 做知识图谱构建？
2. **Embedding 选择**：用硅基流动 API 还是继续用本地模型？
3. **多数据库方案**：单实例+标签过滤 还是 多实例？
4. **旧系统处理**：旧服务已删除，项目统一使用 rag-anything-api 8003。
5. **优先级**：是否立即开始迁移，还是先独立测试 RAG-Anything？

---

**文档创建时间**: 2026-05-05
**状态**: 待审批

