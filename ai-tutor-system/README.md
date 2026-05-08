# AI陪练系统 - 智能话术陪练

## 📦 包内容

- ✅ 后端服务 (tutor_backend.py)
- ✅ 前端界面 (static/)
- ✅ 配置文件
- ✅ 启动脚本

## 🎯 功能说明

基于AI和RAG知识库的智能话术陪练系统：
- 🎭 多场景陪练（价格敏感、技术挑剔、决策谨慎、竞品对比）
- 📊 实时评估反馈
- 💬 智能对话生成
- 📝 详细评估报告

## 🚀 快速开始

### 1. 解压
```bash
tar -xzf ai-tutor-system.tar.gz
cd ai-tutor-system
```

### 2. 配置
```bash
# 复制配置模板
cp .env.template .env

# 编辑配置，填入API Key
vim .env
```

### 3. 安装依赖
```bash
pip install -r requirements_tutor.txt
```

### 4. 启动服务

**Windows用户：**
```bash
# 双击运行
start_tutor.bat
```

**Linux/Mac用户：**
```bash
python tutor_backend.py
```

### 5. 打开界面
在浏览器中打开：
```
file:///your_path/static/index.html
```

或直接双击 `static/index.html` 文件

## 📋 使用流程

1. **选择场景** - 选择客户类型（价格敏感、技术挑剔等）
2. **填写信息** - 客户单位、产品名称、对话背景
3. **开始对话** - AI扮演客户，你扮演销售
4. **实时反馈** - 随时暂停查看建议，或查看实时评分
5. **结束报告** - 对话结束后查看详细评估报告

## 🔧 配置说明

### .env文件
```bash
# MiniMax AI配置（必需）
MINIMAX_API_KEY=your_api_key_here
MINIMAX_BASE_URL=https://api.minimax.chat/v1
MINIMAX_MODEL=abab6.5s-chat  # 或其他MiniMax模型

# 服务配置
RAG_SERVICE_URL=http://localhost:8003  # RAG-Anything服务地址
TUTOR_SERVICE_HOST=0.0.0.0
TUTOR_SERVICE_PORT=8002
```

## 📁 目录结构

```
ai-tutor-system/
├── tutor_backend.py          # 后端服务
├── tutor_config.py           # 配置文件
├── requirements_tutor.txt    # 依赖
├── start_tutor.bat          # Windows启动脚本
├── .env.template            # 配置模板
├── static/                  # 前端界面
│   ├── index.html
│   ├── css/
│   └── js/
└── tutor_data/              # 数据目录
    ├── scenarios.json
    ├── sessions/
    └── history/
```

## 🎭 预设场景

### 1. 价格敏感型客户
- 特征：关注预算和成本
- 策略：突出性价比，提供ROI计算

### 2. 技术挑剔型客户
- 特征：关注技术细节和参数
- 策略：提供技术文档，安排技术交流

### 3. 决策谨慎型客户
- 特征：多方比较，关注风险
- 策略：提供案例证明，强调服务保障

### 4. 竞品对比型客户
- 特征：在多家产品间比较
- 策略：突出差异化优势

## 📊 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 开场话术 | 15% | 开场是否自然，是否建立信任 |
| 需求挖掘 | 20% | 是否了解客户真实需求 |
| 产品介绍 | 20% | 产品介绍是否匹配需求 |
| 异议处理 | 25% | 是否有效应对客户质疑 |
| 促成技巧 | 20% | 是否推进成交 |

## 🔌 依赖服务

- **RAG-Anything服务** (http://localhost:8003) - 建议启动
  - 提供产品知识检索
  - 提供话术参考

- **MiniMax AI API** - 必需
  - 生成AI对话
  - 评估话术质量

## 💡 使用技巧

1. **充分利用背景看板** - 右侧显示客户、产品、场景信息
2. **有效使用暂停功能** - 遇到困难时暂停获取建议
3. **认真阅读总结报告** - 了解自己的优势和待改进项
4. **多场景练习** - 全面提升应对能力

## ⚠️ 注意事项

1. 需要配置MiniMax API Key
2. 建议同时启动RAG服务以获得更好体验
3. 首次对话可能需要等待模型加载
4. 对话历史会自动保存在 `tutor_data/sessions/`

## 🌐 API端点

- `POST /session/start` - 开始会话
- `POST /chat` - 发送消息
- `POST /session/end` - 结束会话
- `GET /scenarios` - 获取场景列表
- `GET /history` - 查看历史记录

API文档：http://localhost:8002/docs

---

**版本**: v2.0.0
**端口**: 8002
**依赖**: RAG-Anything知识库服务(8003)、MiniMax AI
**更新时间**: 2026-04-21
