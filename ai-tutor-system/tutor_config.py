"""
AI话术陪练系统配置文件
"""

# 从.env文件加载环境变量
import os
from dotenv import load_dotenv

# 尝试加载.env文件
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"[INFO] 已加载.env配置文件")

# ==================== MiniMax AI配置 ====================
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "your_minimax_api_key_here")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")

# ==================== 服务配置 ====================
# RAG 服务地址
# 统一使用 RAG-Anything 系统（LightRAG + 知识图谱）
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")  # RAG知识库服务地址
DEFAULT_RAG_DATABASE = os.getenv("DEFAULT_RAG_DATABASE", "")
TUTOR_SERVICE_HOST = os.getenv("TUTOR_SERVICE_HOST", "0.0.0.0")
TUTOR_SERVICE_PORT = int(os.getenv("TUTOR_SERVICE_PORT", "8002"))

# ==================== 数据存储 ====================
import os
DATA_DIR = os.path.join(os.path.dirname(__file__), "tutor_data")
SCENARIOS_FILE = os.path.join(DATA_DIR, "scenarios.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# ==================== 陪练配置 ====================
# 默认场景配置
DEFAULT_SCENARIOS = {
    "price_sensitive": {
        "id": "price_sensitive",
        "name": "价格敏感型客户",
        "ai_role": "注重预算的采购经理",
        "user_role": "销售代表",
        "description": "客户对价格敏感，需要突出性价比",
        "customer_traits": [
            "关注预算和成本",
            "会对比竞品价格",
            "需要证明物有所值",
            "说话直接但礼貌"
        ],
        "ai_strategy": [
            "先询问产品的基本功能和价值",
            "自然过渡到价格话题：'那价格方面呢？'",
            "表达预算顾虑：'我们预算有限，能不能优惠？'",
            "对比竞品：'其他家类似产品价格更低'",
            "要求性价比证明：'能具体说说为什么值这个价吗？'"
        ],
        "success_criteria": [
            "突出产品独特价值",
            "提供ROI计算",
            "强调长期收益"
        ]
    },
    "tech_focused": {
        "id": "tech_focused",
        "name": "技术挑剔型客户",
        "ai_role": "技术总监",
        "user_role": "销售代表",
        "description": "客户对技术细节要求高，需要专业解答",
        "customer_traits": [
            "关注技术参数和架构",
            "要求技术细节和实现方式",
            "质疑技术能力和稳定性",
            "说话专业、直接"
        ],
        "ai_strategy": [
            "询问技术架构和实现方式",
            "质疑技术参数：'这个技术指标具体是什么意思？'",
            "要求技术证明：'有相关的技术文档或测试报告吗？'",
            "对比竞品技术：'和XX技术相比有什么优势？'",
            "关注安全性和稳定性：'数据安全怎么保障？'"
        ],
        "success_criteria": [
            "提供技术文档",
            "安排技术交流",
            "展示技术优势"
        ]
    },
    "decision_caution": {
        "id": "decision_caution",
        "name": "决策谨慎型客户",
        "ai_role": "慎重的高管",
        "user_role": "销售代表",
        "description": "客户决策谨慎，需要案例和保障",
        "customer_traits": [
            "多方比较和考察",
            "关注实施风险",
            "需要案例证明",
            "决策周期长",
            "说话谨慎、客气"
        ],
        "ai_strategy": [
            "询问类似客户的成功案例",
            "关注实施过程：'具体怎么实施？需要多长时间？'",
            "询问风险控制：'如果出现问题怎么处理？'",
            "了解售后服务：'后续服务怎么保障？'",
            "表示需要时间考虑：'我需要和团队商量一下'",
            "要求试用或POC：'能不能先试用一下？'"
        ],
        "success_criteria": [
            "提供相关案例",
            "强调服务保障",
            "建立信任关系"
        ]
    },
    "competitor_compare": {
        "id": "competitor_compare",
        "name": "竞品对比型客户",
        "ai_role": "正在对比的客户",
        "user_role": "销售代表",
        "description": "客户在多家产品间比较，需要差异化优势",
        "customer_traits": [
            "了解多家竞品信息",
            "详细对比功能和价格",
            "要求差异化说明",
            "理性、客观"
        ],
        "ai_strategy": [
            "主动提及竞品：'我也看了XX公司的产品'",
            "对比具体功能：'你们的这个功能和XX家比有什么不同？'",
            "对比价格：'价格上XX家更有优势'",
            "质疑差异化：'感觉都差不多，你们的独特优势是什么？'",
            "要求价值证明：'为什么要选择你们而不是XX家？'",
            "询问成功案例：'有哪些客户从XX家转到你们这里的？'"
        ],
        "success_criteria": [
            "突出独特优势",
            "差异化定位",
            "价值对比"
        ]
    }
}

# 评估维度配置
EVALUATION_DIMENSIONS = {
    "opening": {
        "name": "开场话术",
        "weight": 15,
        "description": "开场是否自然，是否建立信任"
    },
    "needs_discovery": {
        "name": "需求挖掘",
        "weight": 20,
        "description": "是否了解客户真实需求和痛点"
    },
    "product_presentation": {
        "name": "产品介绍",
        "weight": 20,
        "description": "产品介绍是否匹配客户需求"
    },
    "objection_handling": {
        "name": "异议处理",
        "weight": 25,
        "description": "是否有效应对客户质疑和异议"
    },
    "closing": {
        "name": "促成技巧",
        "weight": 20,
        "description": "是否推进成交或达成下一步"
    }
}

# 评分等级配置
SCORE_LEVELS = {
    "excellent": {"min": 90, "label": "优秀", "stars": 5},
    "good": {"min": 80, "label": "良好", "stars": 4},
    "satisfactory": {"min": 70, "label": "满意", "stars": 3},
    "needs_improvement": {"min": 60, "label": "待改进", "stars": 2},
    "poor": {"min": 0, "label": "较差", "stars": 1}
}

# ==================== RAG检索配置 ====================
RAG_TOP_K = 5  # 每次检索的知识条数
RAG_SIMILARITY_THRESHOLD = 0.6  # 相似度阈值
RAG_REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "90"))  # RAG-Anything 查询可能较慢

# ==================== 对话配置 ====================
MAX_SESSION_ROUNDS = 20  # 最大对话轮数
SESSION_TIMEOUT = 1800  # 会话超时时间（秒）

# ==================== 日志配置 ====================
import logging
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
