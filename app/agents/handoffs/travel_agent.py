"""
Handoffs 主 Agent
一个 Agent + 中间件实现整个旅行规划流程
"""
from langchain.agents import create_agent
from app.config import settings
from app.core.state import TravelState
from app.core.checkpointer import get_checkpointer
from langchain_openai import ChatOpenAI
from app.tools.mcp_tools import get_all_mcp_tools
from app.core.middleware import create_step_config_middleware
from app.tools.state_transition import (
    record_requirement_tool,
    select_destination_tool,
    select_transport_tool,
    select_accommodation_tool,
    select_food_tool,
    generate_itinerary_tool,
    summarize_budget_tool,
    generate_order_tool,
    ALL_ROLLBACK_TOOLS
)
from app.tools.memory_tools import(
    update_travel_style_tool,
    update_dietary_restriction_tool,
    update_food_preference_tool,
    add_travel_record_tool,
    update_accommodation_preference_tool
)
from app.tools.rag_tools import get_rag_tools  # 导入 RAG 工具
from app.tools.router_query import query_destination_info
from app.tools.transport_query import query_transport_options
from app.utils.logger import app_logger
def get_llm():
    """获取配置好的千问模型"""
    return ChatOpenAI(
        model=settings.qwen_model_name,
        base_url=settings.qwen_base_url,
        api_key=settings.dashscope_api_key,
        temperature=settings.qwen_temperature,
        max_tokens=settings.qwen_max_tokens,
        streaming=True
    )
async def create_travel_agent():
    """
    创建 Handoffs 旅行规划 Agent

    返回：
        编译好的 Agent（可直接调用）
    """

    app_logger.info("创建 Travel Agent...")

    llm = get_llm()
    all_mcp_tools = await get_all_mcp_tools()
    # 异步创建中间件（预加载配置）
    step_config_middleware = await create_step_config_middleware()
    rag_tools = get_rag_tools()
    all_tools = [
        record_requirement_tool,
        select_destination_tool,
        select_transport_tool,
        select_accommodation_tool,
        select_food_tool,
        generate_itinerary_tool,
        summarize_budget_tool,
        generate_order_tool,
        query_destination_info,
        query_transport_options,
        *rag_tools,
        *all_mcp_tools,
        *ALL_ROLLBACK_TOOLS,
        update_travel_style_tool,
        update_dietary_restriction_tool,
        update_food_preference_tool,
        add_travel_record_tool,
        update_accommodation_preference_tool
    ]

    checkpointer = await get_checkpointer()

    agent = create_agent(
        model=llm,
        tools=all_tools,
        state_schema=TravelState,
        middleware=[step_config_middleware],  # 使用预加载的中间件
        checkpointer=checkpointer,
    )

    app_logger.info("✅ Travel Agent 创建完成")

    return agent