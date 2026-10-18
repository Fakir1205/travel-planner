#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2026/1/7 16:16
@Author  : GGBOND
@File    : transport_coordinator.py
@Software: PyCharm
"""
"""
交通规划协调器（主 Agent）
整合三个 Subagents + 辅助工具
"""
import os
import sys

# 直接运行本文件时（python app/agents/subagents/transport_coordinator.py）让 app 包可导入
if __name__ == "__main__" and __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import asyncio
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from langchain.tools import tool
from app.config import settings
from app.agents.subagents.flight_agent import create_flight_subagent
from app.agents.subagents.train_agent import create_train_subagent
from app.agents.subagents.driving_agent import create_driving_subagent
from app.mcp_core.client import get_mcp_client
from app.utils.logger import app_logger


# ============== 获取辅助工具 ==============

async def _get_auxiliary_tools():
    """获取辅助工具"""
    manager = await get_mcp_client()
    all_tools = await manager.get_tools()

    # 筛选辅助工具
    aux_tools = [
        tool for tool in all_tools
        if any(keyword in tool.name.lower() for keyword in [
            'getfutureweather', 'get-current-date',
            'maps_around_search'
        ])
    ]

    app_logger.info(f"🛠️ 辅助工具: {[t.name for t in aux_tools]}")
    return aux_tools


# ============== 创建交通规划主 Agent ==============

async def create_transport_coordinator():
    """
    创建交通规划协调器（主 Agent）

    整合：
    - 3个子Agent工具（航班、高铁、自驾）
    - MCP辅助工具（酒店、天气、日期、周边搜索）
    """

    llm = ChatTongyi(
        model=settings.qwen_model_name,
        api_key=settings.dashscope_api_key,
        temperature=0.7
    )

    # 异步创建子Agents
    flight_subagent = await create_flight_subagent()
    train_subagent = await create_train_subagent()
    driving_subagent = await create_driving_subagent()

    # ============== 将 Subagents 包装为 Tools ==============

    @tool("query_flights", description="查询航班信息。需要提供出发城市、目的地城市、出发日期。")
    async def query_flights_tool(
        origin: str,
        destination: str,
        departure_date: str
    ) -> str:
        """查询航班信息（调用航班 Subagent）"""

        app_logger.info(f"🔧 调用航班 Subagent: {origin} -> {destination}")

        result = await flight_subagent.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": f"请查询从 {origin} 到 {destination} 的航班，出发日期是 {departure_date}。"
                }
            ]
        })

        return result["messages"][-1].content

    @tool("query_trains", description="查询高铁/火车信息。需要提供出发城市、目的地城市、出发日期。")
    async def query_trains_tool(
        origin: str,
        destination: str,
        departure_date: str
    ) -> str:
        """查询高铁信息（调用高铁 Subagent）"""

        app_logger.info(f"🔧 调用高铁 Subagent: {origin} -> {destination}")

        result = await train_subagent.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": f"请查询从 {origin} 到 {destination} 的高铁，出发日期是 {departure_date}。"
                }
            ]
        })

        return result["messages"][-1].content

    @tool("plan_driving_route", description="规划自驾路线。需要提供出发地和目的地（地址或地名）。")
    async def plan_driving_route_tool(
        origin: str,
        destination: str
    ) -> str:
        """规划自驾路线（调用自驾 Subagent）"""

        app_logger.info(f"🔧 调用自驾 Subagent: {origin} -> {destination}")

        result = await driving_subagent.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": f"请规划从 {origin} 到 {destination} 的自驾路线。"
                }
            ]
        })

        return result["messages"][-1].content

    # 获取辅助工具
    auxiliary_tools = await _get_auxiliary_tools()

    # 组合所有工具
    all_tools = [
        query_flights_tool,
        query_trains_tool,
        plan_driving_route_tool,
    ] + auxiliary_tools

    coordinator = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt="""你是交通规划协调专家。

**可用工具**：

**交通查询（主要）**：
1. query_flights：查询航班信息（适合长途，速度快）
2. query_trains：查询高铁信息（适合中短途，舒适便捷）
3. plan_driving_route：规划自驾路线（适合自驾/自由行/想沿途游玩，或作为高铁的备选；返回总距离、预计时长、油费与过路费）

**辅助工具（按需使用）**：
- getFutureWeatherByAirport：查询机场未来天气
- get-current-date：获取今天日期（调用需要时间的工具前,获取实时时间）

**日期处理（最高优先级，严格遵守）**：
- 当用户说的是"今天/明天/后天/下周"等相对日期时，必须按以下顺序执行，绝不能并行：
  1. **第一步**：**只**调用 get-current-date，等待它返回今天的真实日期（格式 yyyy-MM-dd）。
  2. **第二步**：根据返回的真实日期推算出目标日期（例如返回 2026-10-14，"明天"就是 2026-10-15）。
  3. **第三步**：再用这个真实的 yyyy-MM-dd 日期去调用 query_trains（或 query_flights）。
- 严禁把 get-current-date 和 query_trains/query_flights 放在同一轮并行调用。
- 严禁在还没拿到 get-current-date 结果前，给 departure_date 填入任何凭记忆猜测的日期（绝对不要凭记忆写 2023 年之类的日期）。
- 如果用户已经给出明确的日期（如 2026-11-01），直接使用该日期，无需再调用 get-current-date。

**工作流程**：
1. 理解用户的交通需求（出发地、目的地、日期、人数）
2. 按上面的"日期处理"确定真实出发日期
3. 如果用户明确指定交通方式，直接调用对应工具
4. 如果用户未指定，根据距离和场景推荐：
   * < 300km：优先推荐高铁；距离近也可自驾
   * 300-1000km：优先推荐高铁或航班；若用户想自由行/沿途游玩，推荐自驾
   * > 1000km：优先推荐航班或高铁；若用户明确想自驾或想沿途游玩，推荐自驾
5. 出现以下情况时，应**主动推荐并调用** `plan_driving_route` 给出自驾方案：
   * 用户提到"自驾 / 开车 / 自己开车 / 自由行 / 沿途游玩 / 边走边玩 / 想灵活安排（带老人小孩）"等；
   * 距离不算太远（约 500km 以内）且用户想灵活出行；
   * 用户想在沿途停留、深度游
6. 给出交通建议时，如果条件合适，可以**同时**给出高铁、航班、自驾等方案（自驾包含总距离、预计时长、油费与过路费），让用户按时间/价格/灵活性权衡
7. 调用工具后，用清晰格式展示结果
8. 可以主动询问用户偏好（时间优先 / 价格优先 / 是否想沿途自驾游玩）

**注意事项**：
- 用户说的今天/明天之类的词，一律以 get-current-date 返回的时间为准
- 一定要调用工具获取实时信息，不要编造数据
- 如果查询失败，告知用户并提供替代方案
- 高铁和航班需要提供日期，自驾不需要日期
- 不要只默认推荐高铁/航班：当用户有自驾倾向，或想灵活/沿途游玩时，务必给出自驾方案
- 拿到工具返回结果后，直接汇总展示给用户，不要把工具/格式说明复述出来，也不要输出"请稍等/我将立即返回结果"这类空话
"""
    )

    app_logger.info("✅ 交通规划协调器（主 Agent）创建完成")

    return coordinator


if __name__ == "__main__":
    # Windows 控制台默认 GBK，emoji 会触发 UnicodeEncodeError，这里统一切到 UTF-8
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    async def main():
        print("\n" + "=" * 50)
        print("🚀 正在初始化交通规划协调器...")
        print("=" * 50)

        coordinator = await create_transport_coordinator()

        test_query = "我想从北京去上海，明天出发，沿途想停下来欣赏风景，请问什么交通方式最合适？"

        print(f"\n❓ 用户提问: {test_query}")
        print("-" * 30)

        response = await coordinator.ainvoke({
            "messages": [{"role": "user", "content": test_query}]
        })

        print("-" * 30)
        print("✅ 协调器回复:")
        final_message = response["messages"][-1].content
        print(final_message)

        print("\n" + "=" * 50)
        print("测试结束")
        print("=" * 50)

    asyncio.run(main())