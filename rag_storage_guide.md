# RAG文档管理规范

## 📁 文档存放建议

为了便于管理和维护，建议采用以下文件夹结构：

```
d:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\files\
├── business\                    # 商务视频彩铃文档
│   ├── 产品介绍.pdf
│   ├── 销售话术.docx
│   └── 培训资料.pptx
│
├── ccs_gyl\                     # CCS工程文档
│   ├── 工程规范.pdf
│   ├── 操作指引.docx
│   └── 培训课件.pptx
│
└── quantum\                    # 量子计算文档（预留）
    ├── 技术文档.pdf
    └── 研究报告.docx
```

## 🔄 重组文档结构

由于当前 `storage/files` 根目录已有商务视频彩铃文档，建议：

### 方案1：创建子文件夹分类（推荐）

```bash
# 创建分类文件夹
mkdir storage\files\business
mkdir storage\files\ccs_gyl

# 将现有商务视频彩铃文档移到business文件夹
move storage\files\*.pdf storage\files\business\
move storage\files\*.docx storage\files\business\
move storage\files\*.pptx storage\files\business\
```

### 方案2：保持现状，新增ccs_gyl文件夹

```bash
# 只为CCS工程创建文件夹
mkdir storage\files\ccs_gyl
```

## 💡 建议的操作流程

1. **整理现有文档**
   - 将商务视频彩铃文档移到 `storage/files/business/` 子文件夹

2. **创建CCS工程文件夹**
   - 在 `storage/files/` 下创建 `ccs_gyl` 文件夹

3. **导入文档到对应数据库**
   - `storage/files/business/` → `business_video_ringtone`
   - `storage/files/ccs_gyl/` → `ccs_gyl`

4. **查询时指定数据库**
   - 确保指定正确的数据库ID

## 📊 分类管理优势

- ✅ **清晰分类**：不同产品的文档分开存放
- ✅ **便于维护**：更新某个产品时只操作对应文件夹
- ✅ **避免混淆**：不会误删或误用其他产品的文档
- ✅ **扩展性强**：新增产品只需新建子文件夹


