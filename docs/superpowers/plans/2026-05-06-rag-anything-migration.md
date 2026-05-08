# RAG-Anything 迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 RAG-Anything 作为唯一 RAG 服务部署在端口 8003，所有业务链路统一通过该入口访问知识库。

**Architecture:** `rag-anything-api/` 目录包含 FastAPI 服务 + 国产 AI 适配层。适配层将 MiniMax API 包装为 LightRAG 的 LLM 函数，将硅基流动 API 包装为 Embedding 函数。REST 接口兼容现有业务调用格式，ai-tutor-system 通过配置指向 8003。

**Tech Stack:** FastAPI, RAG-Anything (LightRAG), MiniMax API, 硅基流动 API (bge-m3), uvicorn

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `rag-anything-api/config.py` | 配置管理：端口、API 密钥、超时阈值、降级模型 |
| `rag-anything-api/adapters.py` | 国产 AI 适配层：MiniMax LLM 函数 + 硅基流动 Embedding 函数 |
| `rag-anything-api/app.py` | FastAPI 主服务：暴露兼容 REST 接口，调用 RAG-Anything 引擎 |
| `rag-anything-api/start.py` | 启动脚本：检查依赖、启动 uvicorn |
| `rag-anything-api/requirements.txt` | Python 依赖 |
| `rag-anything-api/.env` | API 密钥配置 |
| `ai-tutor-system/tutor_config.py` | 添加切换说明注释（仅注释，不改逻辑） |

---

### Task 1: 项目初始化与环境准备

**Files:**
- Create: `rag-anything-api/requirements.txt`
- Create: `rag-anything-api/.env`
- Create: `rag-anything-api/config.py`

- [ ] **Step 1: 克隆 RAG-Anything 源码**

```bash
cd D:\GitHub_WorkSpace\Test-System
git clone https://github.com/HKUDS/RAG-Anything.git
```

- [ ] **Step 2: 创建 rag-anything-api 目录**

```bash
mkdir rag-anything-api
mkdir rag-anything-api/storage
mkdir rag-anything-api/storage/lightrag
```

- [ ] **Step 3: 创建 requirements.txt**

文件：`rag-anything-api/requirements.txt`

```txt
fastapi>=0.104.0
uvicorn>=0.24.0
python-dotenv>=1.0.0
requests>=2.31.0
raganything>=0.1.0
pydantic>=2.0.0
```

- [ ] **Step 4: 创建 .env 文件**

文件：`rag-anything-api/.env`

```env
# MiniMax LLM
MINIMAX_API_KEY=your_minimax_api_key_here
MINIMAX_MODEL_M27=MiniMax-M2.7
MINIMAX_MODEL_M25=MiniMax-M2.5

# 硅基流动 Embedding
SILICONFLOW_API_KEY=your_siliconflow_api_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn
SILICONFLOW_MODEL=BAAI/bge-m3

# 服务配置
RAG_SERVICE_HOST=0.0.0.0
RAG_SERVICE_PORT=8003

# 超时配置（秒）
LLM_TIMEOUT_M27=120
LLM_TIMEOUT_M25=90
EMBEDDING_TIMEOUT=30
EMBEDDING_BATCH_SIZE=20
```

- [ ] **Step 5: 创建 config.py**

文件：`rag-anything-api/config.py`

```python
"""
RAG-Anything API 配置
"""

import os
from dotenv import load_dotenv

# 加载 .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

# MiniMax LLM
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_MODEL_M27 = os.getenv("MINIMAX_MODEL_M27", "MiniMax-M2.7")
MINIMAX_MODEL_M25 = os.getenv("MINIMAX_MODEL_M25", "MiniMax-M2.5")

# 硅基流动 Embedding
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "BAAI/bge-m3")

# 服务配置
RAG_SERVICE_HOST = os.getenv("RAG_SERVICE_HOST", "0.0.0.0")
RAG_SERVICE_PORT = int(os.getenv("RAG_SERVICE_PORT", "8003"))

# 超时配置
LLM_TIMEOUT_M27 = int(os.getenv("LLM_TIMEOUT_M27", "120"))
LLM_TIMEOUT_M25 = int(os.getenv("LLM_TIMEOUT_M25", "90"))
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "30"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))

# 存储路径
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage", "lightrag")
os.makedirs(STORAGE_DIR, exist_ok=True)

# 数据库 ID 列表（用于标签过滤）
DATABASE_IDS = [
    "business_video_ringtone",
    "ccs_gyl",
    "quantum",
    "keyexams"
]
```

- [ ] **Step 6: 验证目录结构**

```bash
ls -la rag-anything-api/
```

预期输出：包含 `config.py`、`.env`、`requirements.txt`、`storage/` 目录。

- [ ] **Step 7: Commit**

```bash
git add rag-anything-api/config.py rag-anything-api/.env rag-anything-api/requirements.txt
git commit -m "feat(rag-anything): initialize project structure with config"
```

---

### Task 2: MiniMax LLM 适配层

**Files:**
- Create: `rag-anything-api/adapters.py`

- [ ] **Step 1: 编写 MiniMax LLM 适配函数（含降级链）**

文件：`rag-anything-api/adapters.py`

```python
"""
国产 AI 服务适配层
将 MiniMax / 硅基流动 API 包装为 LightRAG 所需的函数接口
"""

import os
import sys
import requests
import logging
from typing import List, Optional

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))
import config

logger = logging.getLogger(__name__)


# ============= MiniMax LLM 适配 =============

def _call_minimax_api(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: list = None,
    model: str = None,
    timeout: int = 120,
    temperature: float = 0.7,
    max_tokens: int = 4096
) -> str:
    """
    调用 MiniMax API 的底层函数

    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        history_messages: 历史消息
        model: 模型名称
        timeout: 超时秒数
        temperature: 温度
        max_tokens: 最大 token 数

    Returns:
        生成的文本

    Raises:
        Exception: API 调用失败时抛出异常
    """
    if not config.MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY 未配置")

    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {config.MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": model or config.MINIMAX_MODEL_M27,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = requests.post(url, headers=headers, json=data, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        if "message" in choice:
            return choice["message"].get("content", "")
        elif "messages" in choice and len(choice["messages"]) > 0:
            return choice["messages"][-1].get("text", "")

    raise Exception(f"MiniMax API 返回异常: {result}")


def minimax_llm_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: list = None,
    **kwargs
) -> str:
    """
    MiniMax LLM 适配函数，兼容 LightRAG 的 llm_model_func 接口

    降级链：
    1. MiniMax-M2.7（超时 120s）→ 重试 1 次
    2. MiniMax-M2.5（超时 90s）→ 重试 1 次
    3. 抛出异常，由上层处理
    """
    if history_messages is None:
        history_messages = []

    # 第一级：MiniMax-M2.7
    try:
        logger.info(f"尝试 MiniMax-M2.7，prompt: {prompt[:50]}...")
        return _call_minimax_api(
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            model=config.MINIMAX_MODEL_M27,
            timeout=config.LLM_TIMEOUT_M27,
            **kwargs
        )
    except Exception as e:
        logger.warning(f"MiniMax-M2.7 调用失败: {e}，重试中...")
        try:
            return _call_minimax_api(
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                model=config.MINIMAX_MODEL_M27,
                timeout=config.LLM_TIMEOUT_M27,
                **kwargs
            )
        except Exception as e2:
            logger.warning(f"MiniMax-M2.7 重试失败: {e2}，降级到 M2.5")

    # 第二级：MiniMax-M2.5
    try:
        logger.info("降级到 MiniMax-M2.5")
        return _call_minimax_api(
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            model=config.MINIMAX_MODEL_M25,
            timeout=config.LLM_TIMEOUT_M25,
            **kwargs
        )
    except Exception as e:
        logger.warning(f"MiniMax-M2.5 调用失败: {e}，重试中...")
        try:
            return _call_minimax_api(
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                model=config.MINIMAX_MODEL_M25,
                timeout=config.LLM_TIMEOUT_M25,
                **kwargs
            )
        except Exception as e2:
            logger.error(f"MiniMax-M2.5 重试也失败: {e2}")
            raise Exception(
                f"大模型调用超时（M2.7 和 M2.5 均失败）。"
                f"最后错误: {e2}。"
                f"是否切换到向量检索模式？"
            )
```

- [ ] **Step 2: 验证语法正确**

```bash
cd D:\GitHub_WorkSpace\Test-System
python -c "import sys; sys.path.insert(0, 'rag-anything-api'); from adapters import minimax_llm_func; print('LLM adapter OK')"
```

预期输出：`LLM adapter OK`

- [ ] **Step 3: Commit**

```bash
git add rag-anything-api/adapters.py
git commit -m "feat(rag-anything): add MiniMax LLM adapter with degradation chain"
```

---

### Task 3: 硅基流动 Embedding 适配层

**Files:**
- Modify: `rag-anything-api/adapters.py`

- [ ] **Step 1: 添加硅基流动 Embedding 适配函数（含分批逻辑）**

在 `rag-anything-api/adapters.py` 末尾追加：

```python
# ============= 硅基流动 Embedding 适配 =============

def _call_embedding_api(texts: List[str], timeout: int = 30) -> List[List[float]]:
    """
    调用硅基流动 Embedding API 的底层函数

    Args:
        texts: 文本列表
        timeout: 超时秒数

    Returns:
        向量列表

    Raises:
        Exception: API 调用失败时抛出异常
    """
    if not config.SILICONFLOW_API_KEY:
        raise ValueError("SILICONFLOW_API_KEY 未配置")

    url = f"{config.SILICONFLOW_BASE_URL}/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {config.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": config.SILICONFLOW_MODEL,
        "input": texts
    }

    response = requests.post(url, headers=headers, json=data, timeout=timeout)
    response.raise_for_status()
    result = response.json()

    # 按 index 排序，确保顺序与输入一致
    embeddings_data = sorted(result["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in embeddings_data]


def _load_local_embedding_model():
    """
    加载本地 Sentence Transformers 模型（降级备用）
    """
    from sentence_transformers import SentenceTransformer
    model_path = os.path.join(
        os.path.dirname(__file__), "..", "rag-anything-api",
        "models", "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    if os.path.exists(model_path):
        return SentenceTransformer(model_path)
    else:
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


def siliconflow_embedding_func(
    texts: List[str],
    batch_size: int = None
) -> List[List[float]]:
    """
    硅基流动 Embedding 适配函数，兼容 LightRAG 的 embedding_func 接口

    特性：
    - 分批请求，避免大文件超时
    - 单批失败重试 1 次
    - API 完全不可用时降级到本地模型

    Args:
        texts: 文本列表
        batch_size: 每批大小，默认从 config 读取

    Returns:
        向量列表，与输入 texts 一一对应
    """
    if batch_size is None:
        batch_size = config.EMBEDDING_BATCH_SIZE

    # 如果文本量小，直接调用
    if len(texts) <= batch_size:
        try:
            logger.info(f"调用硅基流动 Embedding API，{len(texts)} 条文本")
            return _call_embedding_api(texts, timeout=config.EMBEDDING_TIMEOUT)
        except Exception as e:
            logger.warning(f"Embedding API 调用失败: {e}，重试中...")
            try:
                return _call_embedding_api(texts, timeout=config.EMBEDDING_TIMEOUT)
            except Exception as e2:
                logger.warning(f"Embedding API 重试失败: {e2}，降级到本地模型")
                return _local_embedding_fallback(texts)

    # 大批量：分批处理
    all_embeddings = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Embedding 分批处理: 第 {batch_num}/{total_batches} 批，{len(batch)} 条")

        try:
            batch_embeddings = _call_embedding_api(batch, timeout=config.EMBEDDING_TIMEOUT)
            all_embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.warning(f"第 {batch_num} 批 API 调用失败: {e}，重试中...")
            try:
                batch_embeddings = _call_embedding_api(batch, timeout=config.EMBEDDING_TIMEOUT)
                all_embeddings.extend(batch_embeddings)
            except Exception as e2:
                logger.warning(f"第 {batch_num} 批重试失败: {e2}，降级到本地模型")
                local_embeddings = _local_embedding_fallback(batch)
                all_embeddings.extend(local_embeddings)

    return all_embeddings


def _local_embedding_fallback(texts: List[str]) -> List[List[float]]:
    """
    本地 Embedding 降级方案
    使用 Sentence Transformers 的 paraphrase-multilingual-MiniLM-L12-v2
    """
    logger.info(f"使用本地 Embedding 模型处理 {len(texts)} 条文本")
    model = _load_local_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return embeddings.tolist()
```

- [ ] **Step 2: 验证语法正确**

```bash
cd D:\GitHub_WorkSpace\Test-System
python -c "import sys; sys.path.insert(0, 'rag-anything-api'); from adapters import siliconflow_embedding_func; print('Embedding adapter OK')"
```

预期输出：`Embedding adapter OK`

- [ ] **Step 3: Commit**

```bash
git add rag-anything-api/adapters.py
git commit -m "feat(rag-anything): add SiliconFlow embedding adapter with batching and fallback"
```

---

### Task 4: FastAPI 主服务

**Files:**
- Create: `rag-anything-api/app.py`

- [ ] **Step 1: 编写 FastAPI 主服务**

文件：`rag-anything-api/app.py`

```python
"""
RAG-Anything REST API 服务
兼容现有 rag-anything-api 的接口，底层使用 RAG-Anything 引擎
"""

import sys
import io
import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# 设置编码
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))
import config
from adapters import minimax_llm_func, siliconflow_embedding_func

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============= 自定义 UTF-8 响应 =============

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content):
        return json.dumps(
            content, ensure_ascii=False, allow_nan=False,
            indent=None, separators=(",", ":")
        ).encode("utf-8")


# ============= FastAPI 应用初始化 =============

app = FastAPI(
    title="RAG-Anything 智能检索系统",
    description="基于 LightRAG 知识图谱的增强检索服务，兼容 rag-anything-api 接口",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UTF8JSONResponse
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= RAG-Anything 引擎初始化 =============

rag_engine = None

@app.on_event("startup")
async def startup_event():
    """启动时初始化 RAG-Anything 引擎"""
    global rag_engine
    try:
        from raganything import RAGAnything
        logger.info("正在初始化 RAG-Anything 引擎...")
        rag_engine = RAGAnything(
            llm_model_func=minimax_llm_func,
            embedding_func=siliconflow_embedding_func,
            lightrag_kwargs={
                "storage_dir": config.STORAGE_DIR,
            }
        )
        logger.info(f"RAG-Anything 引擎初始化完成，存储目录: {config.STORAGE_DIR}")
    except Exception as e:
        logger.error(f"RAG-Anything 引擎初始化失败: {e}")
        logger.info("服务将继续启动，但查询功能不可用")


# ============= 数据模型 =============

class SearchRequest(BaseModel):
    """搜索请求（兼容 rag-anything-api 格式）"""
    query: str
    n_results: Optional[int] = 10
    database: Optional[str] = None


class MultiSearchRequest(BaseModel):
    """多数据库搜索请求"""
    query: str
    top_k: Optional[int] = 5
    merge_results: Optional[bool] = False


class DocumentIngestRequest(BaseModel):
    """文档导入请求"""
    text: str
    database: Optional[str] = "business_video_ringtone"
    source: Optional[str] = "manual"


# ============= 路由 =============

@app.get("/")
async def root():
    """系统状态"""
    return {
        "status": "running",
        "message": "RAG-Anything 智能检索系统正在运行",
        "version": "2.0.0",
        "engine": "LightRAG + Knowledge Graph",
        "llm": f"MiniMax ({config.MINIMAX_MODEL_M27} → {config.MINIMAX_MODEL_M25})",
        "embedding": f"硅基流动 {config.SILICONFLOW_MODEL}",
        "endpoints": {
            "docs": "/docs",
            "search": "/search",
            "ai_enhanced_search": "/ai_enhanced_search",
            "query": "/query",
            "status": "/status",
            "db_list": "/db/list",
            "db_stats": "/db/stats"
        }
    }


@app.post("/search")
async def search(request: SearchRequest):
    """语义搜索（兼容 rag-anything-api 接口）"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG 引擎未初始化")

    try:
        logger.info(f"搜索请求: query='{request.query}', database={request.database}")

        # 构建查询提示，加入数据库过滤信息
        query = request.query
        if request.database:
            query = f"[数据库: {request.database}] {query}"

        # 使用 naive 模式（纯向量检索，快速）
        result = await rag_engine.aquery(query, mode="naive")

        # 转换为兼容格式
        results = [{
            "text": result,
            "metadata": {
                "source": "rag-anything",
                "database": request.database or "all",
                "mode": "naive"
            },
            "score": 1.0
        }]

        return {
            "query": request.query,
            "results": results[:request.n_results],
            "total_found": len(results)
        }

    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai_enhanced_search")
async def ai_enhanced_search(request: SearchRequest):
    """AI增强搜索（兼容 rag-anything-api 接口，主接口）"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG 引擎未初始化")

    try:
        logger.info(f"AI增强搜索: query='{request.query}', database={request.database}")

        # 使用 mix 模式（知识图谱 + 向量，最全面）
        result = await rag_engine.aquery(request.query, mode="mix")

        # 转换为兼容格式
        results = [{
            "text": result,
            "metadata": {
                "source": "rag-anything",
                "database": request.database or "all",
                "mode": "mix"
            },
            "score": 1.0
        }]

        return {
            "query": request.query,
            "database": request.database,
            "enhanced_queries": [request.query],
            "results": results[:request.n_results],
            "total_found": len(results)
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"AI增强搜索失败: {error_msg}")

        # 检查是否是 LLM 超时错误
        if "大模型调用超时" in error_msg:
            return {
                "query": request.query,
                "database": request.database,
                "enhanced_queries": [],
                "results": [],
                "total_found": 0,
                "error": "llm_timeout",
                "error_detail": error_msg,
                "message": "大模型调用超时，是否切换到向量检索模式？"
            }

        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/query")
async def query(request: SearchRequest):
    """RAG增强查询（兼容 rag-anything-api 接口）"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG 引擎未初始化")

    try:
        logger.info(f"RAG查询: query='{request.query}'")

        result = await rag_engine.aquery(request.query, mode="hybrid")

        return {
            "query": request.query,
            "context": result,
            "sources": [{"source": "rag-anything", "database": request.database or "all"}],
            "results": [{
                "text": result,
                "metadata": {"source": "rag-anything", "mode": "hybrid"},
                "score": 1.0
            }]
        }

    except Exception as e:
        logger.error(f"RAG查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def status():
    """系统状态"""
    engine_status = "ready" if rag_engine else "not_initialized"

    return {
        "status": "running",
        "engine": engine_status,
        "message": "RAG-Anything 智能检索系统",
        "llm": {
            "primary": config.MINIMAX_MODEL_M27,
            "fallback": config.MINIMAX_MODEL_M25,
            "timeout_m27": config.LLM_TIMEOUT_M27,
            "timeout_m25": config.LLM_TIMEOUT_M25
        },
        "embedding": {
            "provider": "硅基流动",
            "model": config.SILICONFLOW_MODEL,
            "batch_size": config.EMBEDDING_BATCH_SIZE,
            "timeout": config.EMBEDDING_TIMEOUT
        },
        "storage": {
            "path": config.STORAGE_DIR
        }
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy", "engine": "ready" if rag_engine else "not_initialized"}


@app.get("/db/list")
async def list_databases():
    """数据库列表（兼容 rag-anything-api 接口）"""
    databases = []
    for db_id in config.DATABASE_IDS:
        databases.append({
            "id": db_id,
            "name": db_id,
            "status": "active"
        })

    return {
        "status": "success",
        "count": len(databases),
        "databases": databases
    }


@app.get("/db/stats")
async def get_all_database_stats():
    """所有数据库统计（兼容 rag-anything-api 接口）"""
    stats = {}
    for db_id in config.DATABASE_IDS:
        stats[db_id] = {
            "name": db_id,
            "status": "active",
            "engine": "rag-anything",
            "note": "统计信息由 RAG-Anything 引擎管理"
        }

    return {
        "status": "success",
        "databases": stats
    }


@app.get("/db/{db_id}/stats")
async def get_database_stats(db_id: str):
    """指定数据库统计"""
    if db_id not in config.DATABASE_IDS:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")

    return {
        "status": "success",
        "database": {
            "id": db_id,
            "name": db_id,
            "engine": "rag-anything",
            "note": "统计信息由 RAG-Anything 引擎管理"
        }
    }


@app.post("/db/search")
async def multi_database_search(request: MultiSearchRequest):
    """多数据库搜索（兼容 rag-anything-api 接口）"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG 引擎未初始化")

    try:
        result = await rag_engine.aquery(request.query, mode="mix")

        results = [{
            "text": result,
            "metadata": {"source": "rag-anything", "mode": "mix"},
            "score": 1.0
        }]

        return {
            "query": request.query,
            "results": results[:request.top_k],
            "total_found": len(results),
            "merged": request.merge_results
        }

    except Exception as e:
        logger.error(f"多数据库搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= 文档导入 =============

@app.post("/ingest/text")
async def ingest_text(request: DocumentIngestRequest):
    """导入单条文本到知识库"""
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG 引擎未初始化")

    try:
        # 在文本前加入数据库标识，便于后续过滤
        tagged_text = f"[数据库: {request.database}] [来源: {request.source}] {request.text}"

        await rag_engine.ainsert(tagged_text)

        logger.info(f"文本导入成功: database={request.database}, source={request.source}")
        return {
            "status": "success",
            "database": request.database,
            "source": request.source,
            "message": "文本已导入知识库"
        }

    except Exception as e:
        logger.error(f"文本导入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= 启动入口 =============

def check_port_available(port):
    """检查端口是否可用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except socket.error:
            return False


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  RAG-Anything 智能检索系统")
    print("=" * 60)
    print()
    print(f"  LLM: {config.MINIMAX_MODEL_M27} → {config.MINIMAX_MODEL_M25}")
    print(f"  Embedding: 硅基流动 {config.SILICONFLOW_MODEL}")
    print(f"  存储: {config.STORAGE_DIR}")
    print()

    if not check_port_available(config.RAG_SERVICE_PORT):
        print(f"[ERROR] 端口 {config.RAG_SERVICE_PORT} 已被占用！")
        sys.exit(1)

    print(f"  API地址: http://{config.RAG_SERVICE_HOST}:{config.RAG_SERVICE_PORT}")
    print(f"  API文档: http://{config.RAG_SERVICE_HOST}:{config.RAG_SERVICE_PORT}/docs")
    print()

    uvicorn.run(
        app,
        host=config.RAG_SERVICE_HOST,
        port=config.RAG_SERVICE_PORT,
        log_level="info"
    )
```

- [ ] **Step 2: 验证语法正确**

```bash
cd D:\GitHub_WorkSpace\Test-System
python -c "import sys; sys.path.insert(0, 'rag-anything-api'); from app import app; print('App loaded OK')"
```

预期输出：`App loaded OK`

- [ ] **Step 3: Commit**

```bash
git add rag-anything-api/app.py
git commit -m "feat(rag-anything): add FastAPI server with compatible REST endpoints"
```

---

### Task 5: 启动脚本

**Files:**
- Create: `rag-anything-api/start.py`

- [ ] **Step 1: 编写启动脚本**

文件：`rag-anything-api/start.py`

```python
"""
RAG-Anything API 启动脚本
自动检查依赖并启动服务
"""

import sys
import os
import subprocess
import importlib

# 切换到脚本所在目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def check_dependency(module_name, package_name=None):
    """检查 Python 依赖是否安装"""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        pkg = package_name or module_name
        print(f"[MISSING] {pkg} 未安装")
        return False


def main():
    print("=" * 60)
    print("  RAG-Anything API 启动检查")
    print("=" * 60)
    print()

    # 检查核心依赖
    deps = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("dotenv", "python-dotenv"),
        ("requests", "requests"),
        ("pydantic", "pydantic"),
    ]

    missing = []
    for module, package in deps:
        if not check_dependency(module, package):
            missing.append(package)

    # 检查 RAG-Anything（可选，可能未安装）
    rag_available = check_dependency("raganything", "raganything")
    if not rag_available:
        print("[WARN] raganything 未安装，RAG 引擎将不可用")
        print("[WARN] 请运行: pip install raganything")

    if missing:
        print()
        print(f"[ERROR] 缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        sys.exit(1)

    # 检查 .env 文件
    if not os.path.exists(".env"):
        print("[WARN] .env 文件不存在，请复制 .env.example 并填写 API 密钥")
        sys.exit(1)

    print("[OK] 依赖检查通过")
    print()

    # 启动服务
    print("正在启动 RAG-Anything API 服务...")
    print()

    import uvicorn
    import config

    uvicorn.run(
        "app:app",
        host=config.RAG_SERVICE_HOST,
        port=config.RAG_SERVICE_PORT,
        log_level="info",
        reload=False
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add rag-anything-api/start.py
git commit -m "feat(rag-anything): add startup script with dependency checks"
```

---

### Task 6: 安装依赖与验证启动

- [ ] **Step 1: 安装 RAG-Anything**

```bash
cd D:\GitHub_WorkSpace\Test-System
pip install raganything
```

- [ ] **Step 2: 安装其他依赖**

```bash
pip install fastapi uvicorn python-dotenv requests pydantic
```

- [ ] **Step 3: 填写 .env 中的 API 密钥**

编辑 `rag-anything-api/.env`，填入真实的 MiniMax API Key 和硅基流动 API Key。

- [ ] **Step 4: 尝试启动服务（不带 RAG 引擎）**

```bash
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python start.py
```

预期：服务启动在 8003 端口，`/status` 返回引擎状态为 `not_initialized`（因为可能 RAG-Anything 安装有问题需要调试）。

- [ ] **Step 5: 测试基础接口**

```bash
curl http://localhost:8003/
curl http://localhost:8003/status
curl http://localhost:8003/db/list
curl http://localhost:8003/health
```

预期：所有接口返回 JSON 响应。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(rag-anything): install dependencies and verify startup"
```

---

### Task 7: 知识库数据迁移

**Files:**
- Create: `rag-anything-api/migrate_data.py`

- [ ] **Step 1: 编写数据导出脚本**

文件：`rag-anything-api/migrate_data.py`

```python
"""
从原有 LightRAG 数据导出文档，准备导入到 RAG-Anything
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LightRAG 数据目录
LightRAG_PATHS = {
    "business_video_ringtone": os.path.join(
        os.path.dirname(__file__), "..", "rag-anything-api", "storage", "vectors", "business", "video_ringtone"
    ),
    "ccs_gyl": os.path.join(
        os.path.dirname(__file__), "..", "rag-anything-api", "storage", "vectors", "projects", "ccs_gyl"
    ),
    "keyexams": os.path.join(
        os.path.dirname(__file__), "..", "rag-anything-api", "storage", "vectors", "projects", "keyexams"
    ),
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "migration_data")


def export_database(db_id: str, db_path: str) -> list:
    """从 LightRAG 导出所有文档"""
    try:
        import LightRAG
        from LightRAG.config import Settings

        if not os.path.exists(db_path):
            logger.warning(f"数据库路径不存在: {db_path}")
            return []

        client = LightRAG.PersistentClient(path=db_path)

        # 获取所有 collection
        collections = client.list_collections()
        logger.info(f"数据库 {db_id}: 找到 {len(collections)} 个 collection")

        all_documents = []
        for collection in collections:
            try:
                # 获取所有文档
                result = collection.get(include=["documents", "metadatas"])
                docs = result.get("documents", [])
                metadatas = result.get("metadatas", [])

                for i, doc in enumerate(docs):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    all_documents.append({
                        "text": doc,
                        "metadata": metadata,
                        "database_id": db_id,
                        "collection": collection.name
                    })

                logger.info(f"  Collection '{collection.name}': {len(docs)} 条文档")
            except Exception as e:
                logger.error(f"  Collection '{collection.name}' 导出失败: {e}")

        return all_documents

    except Exception as e:
        logger.error(f"数据库 {db_id} 导出失败: {e}")
        return []


def main():
    """导出所有数据库"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_docs = 0
    for db_id, db_path in LightRAG_PATHS.items():
        logger.info(f"\n导出数据库: {db_id}")
        documents = export_database(db_id, db_path)

        if documents:
            output_file = os.path.join(OUTPUT_DIR, f"{db_id}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(documents, f, ensure_ascii=False, indent=2)
            logger.info(f"  已保存到: {output_file} ({len(documents)} 条)")
            total_docs += len(documents)
        else:
            logger.warning(f"  数据库 {db_id} 无数据或导出失败")

    logger.info(f"\n导出完成！共 {total_docs} 条文档")
    logger.info(f"输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行导出脚本**

```bash
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python migrate_data.py
```

预期：在 `rag-anything-api/migration_data/` 目录下生成 JSON 文件。

- [ ] **Step 3: 检查导出结果**

```bash
ls -la migration_data/
python -c "import json; d=json.load(open('migration_data/business_video_ringtone.json','r',encoding='utf-8')); print(f'business_video_ringtone: {len(d)} 条')"
```

- [ ] **Step 4: Commit**

```bash
git add rag-anything-api/migrate_data.py
git commit -m "feat(rag-anything): add data migration script for LightRAG export"
```

---

### Task 8: 知识库数据导入

**Files:**
- Create: `rag-anything-api/import_data.py`

- [ ] **Step 1: 编写数据导入脚本**

文件：`rag-anything-api/import_data.py`

```python
"""
将导出的数据导入到 RAG-Anything 知识库
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import config
from adapters import minimax_llm_func, siliconflow_embedding_func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATION_DIR = os.path.join(os.path.dirname(__file__), "migration_data")


async def import_database(rag, db_id: str, documents: list):
    """将一个数据库的所有文档导入 RAG-Anything"""
    logger.info(f"\n导入数据库: {db_id} ({len(documents)} 条)")

    success_count = 0
    fail_count = 0

    for i, doc in enumerate(documents):
        text = doc.get("text", "")
        if not text or len(text.strip()) < 10:
            continue

        # 在文本前加入数据库标识
        tagged_text = f"[数据库: {db_id}] {text}"

        try:
            await rag.ainsert(tagged_text)
            success_count += 1
            if (i + 1) % 10 == 0:
                logger.info(f"  进度: {i + 1}/{len(documents)} (成功: {success_count})")
        except Exception as e:
            fail_count += 1
            if fail_count <= 5:
                logger.warning(f"  第 {i + 1} 条导入失败: {str(e)[:100]}")

    logger.info(f"  完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count, fail_count


async def main():
    """导入所有数据"""
    if not os.path.exists(MIGRATION_DIR):
        logger.error(f"迁移数据目录不存在: {MIGRATION_DIR}")
        logger.error("请先运行 migrate_data.py 导出数据")
        return

    # 初始化 RAG-Anything
    try:
        from raganything import RAGAnything
        logger.info("初始化 RAG-Anything 引擎...")
        rag = RAGAnything(
            llm_model_func=minimax_llm_func,
            embedding_func=siliconflow_embedding_func,
            lightrag_kwargs={"storage_dir": config.STORAGE_DIR}
        )
    except Exception as e:
        logger.error(f"RAG-Anything 初始化失败: {e}")
        return

    # 按优先级导入
    priority_order = [
        "business_video_ringtone",  # 高优先级
        "ccs_gyl",                  # 中优先级
        "keyexams",                 # 中优先级
    ]

    total_success = 0
    total_fail = 0

    for db_id in priority_order:
        json_file = os.path.join(MIGRATION_DIR, f"{db_id}.json")
        if not os.path.exists(json_file):
            logger.warning(f"跳过 {db_id}: 文件不存在")
            continue

        with open(json_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)

        success, fail = await import_database(rag, db_id, documents)
        total_success += success
        total_fail += fail

    logger.info(f"\n导入完成！总计: 成功 {total_success}, 失败 {total_fail}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 运行导入脚本**

```bash
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python import_data.py
```

预期：数据导入到 RAG-Anything 的 LightRAG 存储中。注意此步骤会调用 MiniMax API 进行知识图谱构建，可能需要较长时间。

- [ ] **Step 3: Commit**

```bash
git add rag-anything-api/import_data.py
git commit -m "feat(rag-anything): add data import script for RAG-Anything indexing"
```

---

### Task 9: 端到端集成测试

- [ ] **Step 1: 启动 rag-anything-api 服务**

```bash
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python start.py
```

- [ ] **Step 2: 测试基础接口**

```bash
curl http://localhost:8003/
curl http://localhost:8003/status
curl http://localhost:8003/db/list
```

预期：所有接口正常返回 JSON。

- [ ] **Step 3: 测试搜索接口**

```bash
curl -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query": "商务视频彩铃价格", "database": "business_video_ringtone"}'
```

预期：返回搜索结果。

- [ ] **Step 4: 测试 AI 增强搜索接口**

```bash
curl -X POST http://localhost:8003/ai_enhanced_search \
  -H "Content-Type: application/json" \
  -d '{"query": "商务视频彩铃产品介绍", "database": "business_video_ringtone"}'
```

预期：返回 AI 增强搜索结果。

- [ ] **Step 5: 切换 ai-tutor-system 到新服务**

编辑 `ai-tutor-system/tutor_config.py`，将 `RAG_SERVICE_URL` 改为 `http://localhost:8003`。

- [ ] **Step 6: 启动 ai-tutor-system 并测试完整陪练流程**

```bash
cd D:\GitHub_WorkSpace\Test-System\ai-tutor-system
python tutor_backend.py
```

在浏览器中打开 `http://localhost:8002`，完成一次完整陪练：
1. 选择场景
2. 对话 3-5 轮
3. 结束并查看报告

- [ ] **Step 7: 验证新知识库效果**

使用相同场景在 8003 服务上验证：
- 搜索结果相关性
- AI 回复质量
- 响应速度

- [ ] **Step 8: Commit 测试结果**

```bash
git add -A
git commit -m "test(rag-anything): complete end-to-end integration test"
```

---

### Task 10: 更新文档与清理

- [ ] **Step 1: 在 tutor_config.py 添加切换说明注释**

在 `ai-tutor-system/tutor_config.py` 第 20 行附近添加注释：

```python
# RAG 服务地址
# 当前唯一知识库入口：RAG-Anything 服务
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")
```

- [ ] **Step 2: 更新 SESSION.md**

更新 `SESSION.md` 记录迁移完成状态。

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "docs(rag-anything): update config comments and session notes"
```

