"""
TravelState 状态定义
使用 TypedDict + Annotated 实现类型安全和状态合并
"""
from typing import Annotated, Literal, Optional
from typing_extensions import  TypedDict,NotRequired
from operator import add
from langchain.agents import AgentState
PlanningStep = Literal[
    "requirement_collection",       # 需求收集
    "destination_recommendation",   # 目的地推荐
    "transport_planning",           # 交通规划
    "accommodation_planning",       # 住宿规划
    "food_planning",                # 餐饮规划
    "itinerary_generation",         # 行程生成
    "budget_summarization",         # 预算汇总
    #"report_generation"             # 报告生成
    "order_generation"             # 订单生成
]
TravelStyle = Literal[
    "relaxation",   # 休闲度假
    "culture",      # 文化探索
    "adventure",    # 户外冒险
    "food"          # 美食之旅
]
BudgetLevel = Literal[
    "economy",  # 经济型（< 3000元/人）
    "comfort",  # 舒适型（3000-8000元/人）
    "luxury"    # 豪华型（> 8000元/人）
]
TransportType = Literal[
    "flight",   # 航班
    "train",    # 高铁/火车
    "driving"   # 自驾
]
AccommodationType = Literal[
    "star_hotel",
    "economy_hotel",
    "hostel",
    "youth_hostel",
]
FoodType = Literal[
    "specialty",
    "chain",
    "local"
]
class UserRequirement(TypedDict):
    """用户旅行需求"""
    departure_city: str             # 出发地点
    destination: str                # 目的地
    departure_date: str             # 出发日期（YYYY-MM-DD）
    travel_days: int                # 出行天数
    adult_count: int                # 成人数量
    children_count: int             # 儿童数量
    budget_min: Optional[float]     # 预算下限
    budget_max: Optional[float]     # 预算上限
    budget_level: BudgetLevel       # 预算等级
    travel_styles: list[TravelStyle]# 旅行风格（多选）
    special_needs: Optional[str]    # 特殊需求（文本）
class DestinationInfo(TypedDict):
    """目的地信息"""
    name: str #目的地名字
    description: str #目的地具体描述
    weather_info: Optional[str]  # 天气信息
    attractions: list[str]  # 景点列表
    estimated_cost: Optional[float]  # 预估花费
class TransportInfo(TypedDict):
    """交通信息"""
    transport_type: TransportType #交通类型
    details: str #具体信息（航班/车次）
    departure_time: str
    arrival_time: str
    duration: str
    price: float
class AccommodationInfo(TypedDict):
    """住宿信息"""
    name: str
    type: AccommodationType
    location: str
    price_per_night: float
    rating: Optional[float]
    amenities: list[str]
class FoodInfo(TypedDict):
    type: FoodType
    recommendations: list[str]
    estimated_daily_cost: float
class ItineraryDay(TypedDict):
    """单日行程"""
    day_number: int
    activities: list[str]
    meals: list[str]
    accommodation: str
class BudgetBreakdown(TypedDict):
    """预算明细"""
    transport: float
    accommodation: float
    food: float
    attractions: float
    misc: float
    total: float
class TravelState(AgentState):
    """旅行规划助手主状态"""
    current_step: NotRequired[PlanningStep]  # 当前步骤
    user_requirement: NotRequired[UserRequirement]#用户需求
    #--------------------------用户选择的类型
    selected_destination: NotRequired[str]  # 选中的目的地
    selected_transport: NotRequired[TransportType]  # 选中的交通方式
    selected_accommodation_types: NotRequired[list[AccommodationType]]  # 选中的住宿类型（多选）
    selected_food_types: NotRequired[list[FoodType]]  # 选中的餐饮类型（多选）
    #--------------------------通过选择最终筛选的类型
    destination_options: NotRequired[list[DestinationInfo]]  # 目的地选项
    transport_options: NotRequired[list[TransportInfo]]  # 交通选项
    accommodation_options: NotRequired[list[AccommodationInfo]]  # 住宿选项
    food_options: NotRequired[list[FoodInfo]]  # 餐饮选项
    #--------------------------最终结果
    itinerary: NotRequired[list[ItineraryDay]]  # 根据选择的类型做出的行程安排
    budget: NotRequired[BudgetBreakdown]  # 预算明细
    report: NotRequired[str]  # 旅行报告（Markdown 格式）
    # order_id: NotRequired[str]                 # 订单号
    #-------------------------审批状态
    approval_pending: NotRequired[bool]  # 是否等待审批
    approval_reason: NotRequired[str]  # 审批原因
    #-------------------------用户元数据
    user_id: NotRequired[str]  # 用户 ID
    session_id: NotRequired[str]  # 会话 ID
    created_at: NotRequired[float]  # 创建时间（Unix 时间戳）
    updated_at: NotRequired[float]  # 更新时间
def create_initial_state(user_id: str, session_id: str) -> TravelState:
    """创建初始状态"""
    import time

    return TravelState(
        messages=[],
        current_step="requirement_collection",
        destination_options=[],
        transport_options=[],
        accommodation_options=[],
        food_options=[],
        approval_pending=False,
        user_id=user_id,
        session_id=session_id,
        created_at=time.time(),
        updated_at=time.time()
    )
