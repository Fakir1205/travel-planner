"""
测试交通规划 Subagents 系统
"""
import pytest
import asyncio
from app.agents.subagents.transport_coordinator import create_transport_coordinator

@pytest.mark.asyncio
async def test_flight_query():
    """测试航班查询（主 Agent 调用航班 Subagent）"""

    coordinator = create_transport_coordinator()

    print("\n=== 测试航班查询 ===")

    response = await coordinator.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": "我想从北京飞到上海，8月1日出发，2个人，请帮我查询航班。"
            }
        ]
    })

    print(f"\n协调器响应：\n{response['messages'][-1].content}")

    print("\n✅ 航班查询测试完成")

@pytest.mark.asyncio
async def test_train_query():
    """测试高铁查询"""

    coordinator = create_transport_coordinator()

    print("\n=== 测试高铁查询 ===")

    response = await coordinator.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": "北京到西安，8月1日，坐高铁，帮我查一下车次。"
            }
        ]
    })

    print(f"\n协调器响应：\n{response['messages'][-1].content}")

    print("\n✅ 高铁查询测试完成")

@pytest.mark.asyncio
async def test_driving_route():
    """测试自驾路线"""

    coordinator = create_transport_coordinator()

    print("\n=== 测试自驾路线 ===")

    response = await coordinator.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": "我打算自驾从北京到上海，帮我规划一下路线。"
            }
        ]
    })

    print(f"\n协调器响应：\n{response['messages'][-1].content}")

    print("\n✅ 自驾路线测试完成")

@pytest.mark.asyncio
async def test_auto_recommendation():
    """测试主 Agent 自动推荐交通方式"""

    coordinator = create_transport_coordinator()

    print("\n=== 测试自动推荐 ===")

    response = await coordinator.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": "我想从北京去西安，8月1日出发，有什么推荐的交通方式吗？"
            }
        ]
    })

    print(f"\n协调器响应：\n{response['messages'][-1].content}")

    print("\n✅ 自动推荐测试完成")


if __name__ == "__main__":
    asyncio.run(test_flight_query())
    asyncio.run(test_train_query())
    asyncio.run(test_driving_route())
    asyncio.run(test_auto_recommendation())