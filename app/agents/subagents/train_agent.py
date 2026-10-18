"""
高铁查询 Subagent
调用 12306 MCP 的多个工具
"""
import os
import sys

# 直接运行本文件时（python app/agents/subagents/train_agent.py）让 app 包可导入
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
    1. 对支持 limit 参数的工具注入精简默认值（limit=10）；
    2. 将超长返回文本截断到 max_chars。
    """
    from langchain_core.tools import StructuredTool

    wrapped = []
    for tool in tools:
        schema = tool.args_schema if isinstance(tool.args_schema, dict) else {}
        props = schema.get("properties", {})

        async def _run(tool=tool, props=props, **kwargs):
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


async def _get_railway_tools():
    """获取高铁相关的MCP工具"""
    manager = await get_mcp_client()
    all_tools = await manager.get_tools()

    # 筛选高铁工具
    railway_tools = [
        tool for tool in all_tools
        if any(keyword in tool.name.lower() for keyword in [
            'station', 'ticket', 'train', 'get-current-date'
        ])
    ]

    # 包装工具：精简参数 + 截断超长返回
    railway_tools = _constrain_tools(railway_tools)

    app_logger.info(f"🚄 高铁工具: {[t.name for t in railway_tools]}")
    return railway_tools


async def create_train_subagent():
    """创建高铁查询 Subagent"""

    llm = ChatTongyi(
        model=settings.qwen_model_name,
        api_key=settings.dashscope_api_key,
        temperature=0.1
    )

    # 异步获取工具
    railway_tools = await _get_railway_tools()

    agent = create_agent(
        model=llm,
        tools=railway_tools,
        system_prompt="""你是高铁查询专家，负责处理火车票查询、行程规划及车次详情查询。可以使用以下工具：

**可用工具**：
1.  **日期与基础信息**：
    - `get-current-date`: 获取今日日期（yyyy-MM-dd）。用户提到"明天/下周"时必须先调用此工具。
    - `get-station-code-of-citys`: 用【城市名】（如"北京"）查询对应的车站代码。
    - `get-station-code-by-names`: 用【具体车站名】（如"北京南"）查询对应的车站代码。
    - `get-stations-code-in-city`: 查询某城市内【所有】火车站列表。

2.  **余票查询（核心）**：
    - `get-tickets`: 查询【直达】车次余票。参数：出发/到达代码、日期、车次类型(G/D等)。
    - `get-interline-tickets`: 查询【中转/接续】方案。**当直达无票，或用户明确询问中转时使用此工具**。

3.  **车次详情**：
    - `get-train-route-stations`: 查询某具体车次（如 G101）的【经停站、时刻表】信息。

**查询流程（严格遵守）**：
1.  **日期处理**：解析用户给的日期。若用户说的是"明天/后天/下周"等相对日期，必须先**单独**调用 `get-current-date`，等待结果返回后算出目标日期（不要与其它工具并行调用），再继续后续查询。
    - 若用户已给出明确日期（如 2026-01-17），直接使用，无需调用日期工具。
    - 绝对不能把函数名当参数传入（例如日期不能写成 "get-current-date_result"）。
2.  **地点编码**：
    - 严禁直接将中文地名传给查询接口。
    - 若用户输入是城市（"北京到上海"），用 `get-station-code-of-citys`。
    - 若用户输入是具体车站（"北京南到上海虹桥"），用 `get-station-code-by-names`。
3.  **余票查询策略**：
    - 优先调用 `get-tickets` 查直达。
    - **如果 `get-tickets` 返回无票，或用户询问"有没有中转"，请立即尝试调用 `get-interline-tickets`**。
4.  **经停查询**：仅当用户询问"这趟车经过哪里"或"时刻表"时，使用 `get-train-route-stations`。

**输出格式**：
- 你必须**真正调用**上面的工具来获取数据；**绝不允许编造**工具调用过程或结果（例如不要输出 "Calling get-tickets with params: ..." 这种假的调用文本），也不要编造车次或价格。
- 拿到工具返回的数据后，直接以结构化清晰的方式**汇总**答案，包含：车次、起降时间、时长、各席别余票与价格。
- 不要把工具说明/格式说明复述给用户，也不要回"请稍等/我将立即返回结果"这类空话。
- 如果是中转方案，请清楚标明中转站和换乘时间。
- 如果确实没有查到车次，明确告知用户。
"""
    )

    app_logger.info("✅ 高铁 Subagent 创建完成")
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
        print("🚀 正在初始化高铁查询 Subagent...")
        print("=" * 50)

        train_agent = await create_train_subagent()

        test_query = "帮我查一下今天从北京到上海的火车票"

        print(f"\n❓ 用户提问: {test_query}")
        print("-" * 30)

        response = await train_agent.ainvoke({
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
