# RAG-Anything 知识库管理指南

## 当前统一入口

当前项目知识库服务统一使用 `http://localhost:8003`，底层为 `RAGAnything + MinerU + LightRAG`。

常用接口：

- `GET /db/list`
- `GET /db/stats`
- `GET /db/stats/{database}`
- `POST /search`
- `POST /ai_enhanced_search`
- `POST /context`
- `POST /ingest/path`
- `POST /ingest/text`

## 存储目录

知识库注册表：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\databases.json
```

RAG-Anything 主存储：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\raganything\{database}\rag_storage
```

解析输出：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\output\{database}
```

## 导入文件

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/ingest/path" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    path = "D:\GitHub_WorkSpace\Test-System\商务彩铃"
    database = "商务彩铃"
    recursive = $true
  } | ConvertTo-Json -Compress)
```

## 导入文本

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/ingest/text" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    text = "商务彩铃产品说明"
    database = "商务彩铃"
    source = "manual"
  } | ConvertTo-Json -Compress)
```

## 查询

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/search" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    query = "商务视频彩铃资费是多少"
    database = "商务彩铃"
    n_results = 5
  } | ConvertTo-Json -Compress)
```

## 轻量上下文查询

实时陪练优先使用 `/context`，用于获取知识上下文而不是完整生成答案。

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/context" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    query = "价格异议处理"
    database = "商务彩铃"
    n_results = 5
  } | ConvertTo-Json -Compress)
```

## 注意事项

- 修改配置后需重启 RAG 服务
- 每个数据库有独立的 RAG 存储目录，互不影响
- 删除向量数据前请先备份

---

**更新时间**: 2026-05-08
**版本**: v3.0
