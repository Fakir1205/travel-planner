from datetime import datetime
from jinja2 import Template
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from typing import Callable, Any
from app.core.state import TravelState
from app.core.store import get_user_memory_service
from app.utils.logger import app_logger


class StepConfigMiddleware(AgentMiddleware):
    """
    步骤配置中间件 - 根据 current_step 动态配置 Agent
    """

    def __init__(self, step_config: dict):
        """
        初始化中间件

        Args:
            step_config: 预加载的步骤配置字典
        """
        self._step_config = step_config

    async def awrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        """
        根据 current_step 动态配置 Agent
        """
        # 获取当前步骤
        state: TravelState = request.state
        state_dict = dict(state) if hasattr(state, "items") else {}
        current_step = state.get("current_step", "requirement_collection")
        user_id = state.get("user_id")

        app_logger.info(f"📋 用户ID: {user_id}")
        app_logger.info(f"📍 当前步骤: {current_step}")

        if current_step not in self._step_config:
            app_logger.error(f"❌ 未知步骤: {current_step}")
            raise ValueError(f"未知步骤: {current_step}")

        step_config = self._step_config[current_step]

        # ========== 验证前置依赖 ==========
        for required_field in step_config["requires"]:
            if required_field not in state or state[required_field] is None:
                error_msg = f"步骤 {current_step} 需要完整状态: {required_field} 未设置"
                app_logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)

        # ========== 🔑 核心：注入长期记忆 ==========
        memory_prompt = ""
        if user_id:
            try:
                service = await get_user_memory_service()
                memory_prompt = await service.format_memory_for_prompt(user_id)
                if memory_prompt:
                    app_logger.info(f"💾 已加载用户长期记忆: {user_id}")
                else:
                    app_logger.info(f"📝 用户首次使用，暂无历史记忆: {user_id}")
            except Exception as e:
                app_logger.warning(f"⚠️ 加载长期记忆失败: {e}")

        # ========== 动态填充提示词变量 ==========
        try:
            state_dict["user_memory"] = memory_prompt  # 将记忆注入到模板变量
            template = Template(step_config["prompt"])
            system_prompt = template.render(**state_dict)
            #**state_dict 的作用：这里的 ** 是 Python 的解包操作，
            #它告诉 Jinja2：“把这个字典里的所有 Key 都当作变量名，Value 都当作变量值去替换模板里的内容。”

            # 如果有长期记忆，追加到提示词末尾
            if memory_prompt:
                system_prompt = f"{system_prompt}\n\n{memory_prompt}"

        except KeyError as e:
            app_logger.warning(f"⚠️ 提示词变量缺失: {e}, 使用原始模板")
            system_prompt = step_config["prompt"]

        # ========== 注入当前真实日期（避免模型凭记忆猜测日期） ==========
        now = datetime.now()
        weekday_cn = "一二三四五六日"[now.weekday()]
        system_prompt += (
            f"\n\n【系统时间】今天是 {now.strftime('%Y-%m-%d')}（星期{weekday_cn}）。"
            "涉及“今天/明天/后天/本周/下周”等相对日期的推算，一律以此为准，"
            "不要凭记忆猜测当前日期；如需节假日信息再调用日期工具。"
        )

        # ========== 注入配置 ==========
        modified_request = request.override(
            system_prompt=system_prompt,
            tools=step_config["tools"]
        )

        app_logger.info(f"✅ 已注入步骤配置: {len(step_config['tools'])} 个工具")

        return await handler(modified_request)


async def create_step_config_middleware() -> StepConfigMiddleware:
    """
    工厂函数：创建步骤配置中间件

    Returns:
        预加载配置的 StepConfigMiddleware 实例
    """
    from app.agents.handoffs.step_config import get_step_config

    step_config = await get_step_config()
    return StepConfigMiddleware(step_config)