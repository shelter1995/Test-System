# RAG数据库更换指南

> ⚠️ 重要说明（2026-05-08更新）  
> 当前项目知识库已切换到 **HKUDS/RAG-Anything**，以 `http://localhost:8003` 为唯一入口。  
> 本文中涉及旧向量库目录结构（如 `chroma.sqlite3`、`collection_name`、`/ingest/file`、`/ingest/folder`）的段落已不再适用，请以以下接口为准：
>
> - `GET /db/list`
> - `GET /db/stats/{db_id}`
> - `POST /ai_enhanced_search`（参数：`query`、`database`、`n_results`）
> - `POST /ingest/path`（参数：`path`、`database`、`recursive`）

## 📋 当前数据库状态

**现有数据库**：
- ID: `business_video_ringtone`
- 名称: 商务视频彩铃数据库
- 文档数: 2881个
- 状态: 已启用

---

## 🔄 更换数据库的3种方式

### 方式一：创建新的数据库（推荐）

#### 步骤1：准备文档
将新文档放入指定文件夹：

```
d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\files\
├── 新文档1.pdf
├── 新文档2.docx
└── 其他资料.xlsx
```

#### 步骤2：修改配置文件
编辑 `config.py` 添加新数据库配置：

```python
DATABASE_CONFIGS = {
    # 现有数据库
    "business_video_ringtone": {
        "name": "商务视频彩铃数据库",
        "persist_dir": f"{VECTORS_PATH}/business/video_ringtone",
        "collection_name": "video_ringtone_business_collection",
        "description": "商务视频彩铃相关文档、方案和营销资料",
        "enabled": True
    },

    # ★ 新增：新产品数据库
    "new_product": {
        "name": "新产品数据库",
        "persist_dir": f"{VECTORS_PATH}/new_product",
        "collection_name": "new_product_collection",
        "description": "新产品相关文档",
        "enabled": True  # 启用新数据库
    },

    # 量子计算专用数据库（预留）
    "quantum": {
        "name": "量子",
        "persist_dir": f"{VECTORS_PATH}/projects/quantum",
        "collection_name": "quantum_collection",
        "description": "量子计算相关文档的向量数据库",
        "enabled": False  # 暂不启用
    }
}
```

#### 步骤3：创建向量存储目录
```bash
mkdir -p d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\\lightrag\new_product
```

#### 步骤4：导入文档
使用API导入新文档到指定数据库：

```bash
# 扫描文件夹导入（所有文档自动路由到new_product）
curl -X POST "http://localhost:8003/ingest/folder" ^
  -H "Content-Type: application/json" ^
  -d "{\"folder_path\": \"storage/files\", \"database\": \"new_product\"}"

# 或者导入单个文件
curl -X POST "http://localhost:8003/ingest/file" ^
  -F "file=@新文档.pdf" ^
  -F "database=new_product"
```

#### 步骤5：重启RAG服务
```bash
# 停止服务 (Ctrl+C)
# 重新启动
cd d:\GitHub_WorkSpace\Test-System\rag-anything-api
python app.py
```

---

### 方式二：完全替换现有数据库

如果想用新数据**完全替换**现有的商务视频彩铃数据库：

#### 步骤1：清空现有文档（可选）
删除旧文档和向量数据：

```bash
# 删除向量数据
rm -rf d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\\lightrag\business\video_ringtone\*

# 删除旧文档（谨慎操作）
rm -f d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\files\商务视频彩铃*.pdf
```

#### 步骤2：放入新文档
将新产品文档放入 `storage/files` 文件夹

#### 步骤3：重新导入
```bash
# 扫描整个文件夹重新导入
curl -X POST "http://localhost:8003/ingest/folder" ^
  -H "Content-Type: application/json" ^
  -d "{\"folder_path\": \"storage/files\", \"database\": \"business_video_ringtone\"}"
```

#### 步骤4：重启服务
```bash
python app.py
```

---

### 方式三：多数据库并行使用

系统支持同时运行多个数据库，可以根据需求切换：

#### 添加多个数据库配置
```python
DATABASE_CONFIGS = {
    "product_a": {
        "name": "产品A数据库",
        "persist_dir": f"{VECTORS_PATH}/product_a",
        "collection_name": "product_a_collection",
        "description": "产品A相关文档",
        "enabled": True
    },
    "product_b": {
        "name": "产品B数据库",
        "persist_dir": f"{VECTORS_PATH}/product_b",
        "collection_name": "product_b_collection",
        "description": "产品B相关文档",
        "enabled": True
    },
    "business_video_ringtone": {
        "name": "商务视频彩铃数据库",
        "persist_dir": f"{VECTORS_PATH}/business/video_ringtone",
        "collection_name": "video_ringtone_business_collection",
        "description": "商务视频彩铃相关文档、方案和营销资料",
        "enabled": True
    }
}
```

#### 查询时指定数据库
```bash
# 查询产品A数据库
curl -X POST "http://localhost:8003/search" ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"产品介绍\", \"database\": \"product_a\", \"n_results\": 10}"

# 查询商务视频彩铃数据库
curl -X POST "http://localhost:8003/search" ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"产品介绍\", \"database\": \"business_video_ringtone\", \"n_results\": 10}"
```

---

## 🛠️ 常用操作命令

### 查看数据库列表
```bash
curl -s http://localhost:8003/db/list
```

### 查看数据库统计
```bash
curl -s http://localhost:8003/db/stats/business_video_ringtone
```

### 导入文档
```bash
# 方式1：文件夹导入
curl -X POST "http://localhost:8003/ingest/folder" ^
  -H "Content-Type: application/json" ^
  -d "{\"folder_path\": \"storage/files\"}"

# 方式2：单个文件导入
curl -X POST "http://localhost:8003/ingest/file" ^
  -F "file=@文档.pdf"
```

### 搜索文档
```bash
curl -X POST "http://localhost:8003/search" ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"搜索关键词\", \"database\": \"数据库ID\", \"n_results\": 10}"
```

### 重置数据库
```bash
# 删除向量数据（需重启服务）
rm -rf d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\\lightrag\{数据库ID}\*
```

---

## 📊 数据库文件结构

```
d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\
├── files\                      # 原始文档
│   ├── 文档1.pdf
│   ├── 文档2.docx
│   └── ...
│
└── vectors\                    # 向量数据库
    ├── business\               # 商务视频彩铃数据库
    │   └── video_ringtone\
    │       ├── chroma.sqlite3
    │       ├── data_level0.bin
    │       └── ...
    │
    ├── new_product\           # 新产品数据库（待创建）
    │   ├── chroma.sqlite3
    │   └── ...
    │
    └── product_b\             # 产品B数据库（待创建）
        ├── chroma.sqlite3
        └── ...
```

---

## ⚠️ 注意事项

### 1. 文档格式支持
- ✅ 文档: PDF, DOCX, XLSX, PPTX, TXT, MD
- ✅ 图片: JPG, PNG, BMP, GIF, WebP
- ✅ 音频: MP3, WAV, M4A, FLAC
- ✅ 视频: MP4, AVI, MOV, MKV

### 2. 配置修改后必须重启
修改 `config.py` 后必须重启RAG服务才能生效

### 3. 向量数据库独立性
每个数据库有独立的向量存储目录，互不影响

### 4. 数据安全
删除向量数据前请先备份

### 5. 导入时间
文档越多，导入时间越长。2881个文档可能需要5-10分钟

---

## 🎯 推荐流程

### 场景1：添加新产品线

1. ✅ 在 `config.py` 添加新数据库配置
2. ✅ 创建向量存储目录
3. ✅ 放入新产品文档
4. ✅ 调用导入API
5. ✅ 重启RAG服务
6. ✅ 测试查询新数据库

### 场景2：替换旧产品数据

1. ✅ 清空旧向量数据
2. ✅ 删除或归档旧文档
3. ✅ 放入新文档
4. ✅ 调用导入API
5. ✅ 重启服务
6. ✅ 验证数据完整性

---

## 📞 故障排除

### 问题1：数据库未显示
```bash
# 检查配置是否启用
grep -A 5 "enabled.*True" config.py

# 检查向量目录是否存在
ls -la storage/lightrag/{数据库ID}
```

### 问题2：导入失败
```bash
# 检查文档格式
file storage/files/文档.pdf

# 检查文件权限
ls -l storage/files/
```

### 问题3：查询无结果
```bash
# 检查文档数量
curl -s http://localhost:8003/db/stats/{数据库ID}

# 尝试搜索通用词
curl -X POST "http://localhost:8003/search" ^
  -d "{\"query\": \"产品\", \"database\": \"{数据库ID}\", \"n_results\": 3}"
```

---

## 🚀 快速参考表

| 操作 | 命令/步骤 | 备注 |
|------|-----------|------|
| 查看数据库 | `curl -s http://localhost:8003/db/list` | 查看所有数据库 |
| 查看统计 | `curl -s http://localhost:8003/db/stats/{id}` | 查看指定数据库详情 |
| 导入文件夹 | `POST /ingest/folder` | 批量导入 |
| 导入文件 | `POST /ingest/file` | 单个文件导入 |
| 搜索 | `POST /search` | 语义搜索 |
| 重启服务 | `python app.py` | 配置修改后必须重启 |

---

**更新时间**: 2026-04-20
**版本**: v1.0


