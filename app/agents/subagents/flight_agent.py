"""
航班查询 Subagent
调用 Aviation MCP 的多个工具
"""
import os
import sys

# 直接运行本文件时（python app/agents/subagents/flight_agent.py）让 app 包可导入
if __name__ == "__main__" and __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import asyncio
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from app.config import settings
from app.mcp_core.client import get_mcp_client
from app.utils.logger import app_logger

# 工具返回结果的字符上限，超过则截断，避免撑爆模型上下文
_MAX_TOOL_CHARS = 8000


def _constrain_tools(tools, max_chars: int = _MAX_TOOL_CHARS):
    """
    包装 MCP 工具，避免返回结果过大导致模型上下文超限 / 答非所问：
    1. 对支持 detail / limit 参数的工具注入精简默认值（detail='summary'、limit=10）；
    2. 将超长返回文本截断到 max_chars。
    """
    from langchain_core.tools import StructuredTool

    wrapped = []
    for tool in tools:
        schema = tool.args_schema if isinstance(tool.args_schema, dict) else {}
        props = schema.get("properties", {})

        async def _run(tool=tool, props=props, **kwargs):
            if "detail" in props and not kwargs.get("detail"):
                kwargs["detail"] = "summary"
            if "limit" in props and not kwargs.get("limit"):
                kwargs["limit"] = 10
            result = await tool.ainvoke(kwargs)
            text = result if isinstance(result, str) else str(result)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n...[结果过长已截断，原始长度 {len(text)} 字符]"
            return text

        wrapped.append(
            StructuredTool.from_function(
                coroutine=_run,
                name=tool.name,
                description=tool.description or tool.name,
                args_schema=schema or None,
            )
        )
    return wrapped


async def _get_aviation_tools():
    """获取航班相关的MCP工具"""
    manager = await get_mcp_client()
    all_tools = await manager.get_tools()

    # 筛选航班工具
    aviation_tools = [
        tool for tool in all_tools
        if any(keyword in tool.name.lower() for keyword in [
            'flight', 'aviation', 'searchflights', 'gettodaydate'
        ])
    ]

    # 包装工具：精简参数 + 截断超长返回
    aviation_tools = _constrain_tools(aviation_tools)

    app_logger.info(f"✈️ 航班工具: {[t.name for t in aviation_tools]}")
    return aviation_tools


async def create_flight_subagent():
    """创建航班查询 Subagent"""

    llm = ChatTongyi(
        model=settings.qwen_model_name,
        api_key=settings.dashscope_api_key,
        temperature=0.1
    )

    # 异步获取工具
    aviation_tools = await _get_aviation_tools()

    agent = create_agent(
        model=llm,
        tools=aviation_tools,
        system_prompt="""你是航班查询专家，负责处理航班查询、机票价格比较及航班状态查询。可以使用以下工具：

**可用工具**：
1.  **日期与基础信息**：
    - `getTodayDate`: 获取今天日期（用于用户提供相对日期时）

2.  **航班查询（核心）**：
    - `searchFlightsByDepArr`: 按出发/到达城市查询航班（需IATA三字码）
    - `searchFlightsByNumber`: 按航班号查询航班信息
    - `getFlightTransferInfo`: 查询中转航班信息
    - `searchFlightItineraries`: 查询可购买航班行程和最低价

**IATA三字码示例**：
- 城市码：北京=BJS, 上海=SHA, 广州=CAN, 西安=XIY, 成都=CTU
- 机场码：首都机场=PEK, 浦东=PVG, 虹桥=SHA

**工作流程（严格遵守）**：
1. 分析用户查询，提取出发地、目的地、日期
2. 如果用户说的是"明天""后天"等相对日期：
   - 第一步：**单独**调用 `getTodayDate`，等待结果返回（不要和其它工具并行调用）
   - 第二步：根据返回的今天日期算出目标日期（如今天是 2026-10-14，明天就是 2026-10-15）
   - 第三步：再用真实的 YYYY-MM-DD 日期调用 `searchFlightsByDepArr`
   - 绝对不能把函数名当参数传入（例如 date 不能写成 "getTodayDate()_result"）
3. 查询航班时**必须**传入精简参数：`detail="summary"`、`limit=10`，只取核心字段，避免返回数据过大
4. 如果查询城市有多个机场，使用depcity/arrcity参数
5. 如果查询具体机场，使用dep/arr参数

**输出格式**：
✈️ 航班 {航班号}
- 出发：{机场} {时间}
- 到达：{机场} {时间}
- 价格：¥{价格}

**注意**：
- 一定要调用工具，不要编造数据
- 日期格式必须是YYYY-MM-DD
- 拿到工具返回的数据后，直接用上面的格式**汇总出航班列表**；不要把工具/格式说明复述给用户，也不要回"请问您想查询哪条航线"这类空话
- 如果没找到航班，明确告知用户
"""
    )

    app_logger.info("✅ 航班 Subagent 创建完成")
    return agent


if __name__ == "__main__":
    # Windows 控制台默认 GBK，emoji 会触发 UnicodeEncodeError，这里统一切到 UTF-8
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    async def main():
        print("\n" + "=" * 50)
        print("🚀 正在初始化航班查询 Subagent...")
        print("=" * 50)

        flight_agent = await create_flight_subagent()

        test_query = "帮我查一下明天从北京到上海的航班"

        print(f"\n❓ 用户提问: {test_query}")
        print("-" * 30)

        response = await flight_agent.ainvoke({
            "messages": [{"role": "user", "content": test_query}]
        })

        print("-" * 30)
        print("✅ Agent 回复:")
        final_message = response["messages"][-1].content
        print(final_message)

        print("\n" + "=" * 50)
        print("测试结束")
        print("=" * 50)


    asyncio.run(main())
