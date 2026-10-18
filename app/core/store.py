"""
PostgreSQL Store 配置
长期记忆（用户级数据持久化）- 修正版
"""
import asyncio
from typing import Optional, List
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from langgraph.store.postgres import AsyncPostgresStore
# from psycopg.rows import dict_row # AsyncPostgresStore 内部处理了 row_factory
from psycopg_pool import AsyncConnectionPool

from app.config import settings
from app.utils.logger import app_logger
from app.core.memory_models import UserProfile, TravelHistory, TravelRecord, UserMemory


class StoreManager:
    """Store 管理器（单例模式）"""

    _instance: Optional['StoreManager'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.store: Optional[AsyncPostgresStore] = None
        self.pool: Optional[AsyncConnectionPool] = None

    @classmethod
    async def get_instance(cls) -> 'StoreManager':
        """获取单例实例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance.initialize()
        return cls._instance

    async def initialize(self):
        """初始化 Store"""

        if self.store is not None:
            app_logger.warning("Store 已初始化，跳过")
            return

        try:
            app_logger.info("初始化 PostgreSQL Store...")

            self.pool = AsyncConnectionPool(
                conninfo=settings.database_url,
                min_size=2,
                max_size=20,
                timeout=30,
                kwargs={"autocommit": True} # LangGraph Store 通常建议 autocommit
            )

            # 打开连接池
            await self.pool.open()

            # 初始化 Store
            self.store = AsyncPostgresStore(self.pool)

            app_logger.info("✅ Store 初始化完成")

        except Exception as e:
            app_logger.error(f"❌ Store 初始化失败: {e}")
            raise

    async def close(self):
        """关闭 Store"""
        if self.store:
            # AsyncPostgresStore 通常不需要显式 close store 对象，
            # 但需要关闭底层的 connection pool
            pass

        if self.pool:
            await self.pool.close()
            app_logger.info("Connection Pool 已关闭")

    def get_store(self) -> AsyncPostgresStore:
        """获取 Store 实例"""
        if self.store is None:
            raise RuntimeError("Store 未初始化，请先调用 initialize()")
        return self.store


# ============== 便捷函数 ==============

async def get_store() -> AsyncPostgresStore:
    """获取全局 Store 实例"""
    manager = await StoreManager.get_instance()
    return manager.get_store()


@asynccontextmanager
async def store_lifespan():
    """Store 生命周期管理器"""
    manager = await StoreManager.get_instance()
    try:
        yield manager.get_store()
    finally:
        await manager.close()


# ============== 用户长期记忆服务 ==============

class UserMemoryService:
    """
    用户长期记忆服务
    提供用户画像和出行历史的 CRUD 操作
    """

    def __init__(self, store: AsyncPostgresStore):
        self.store = store

    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        return datetime.now(timezone.utc).isoformat()

    # ========== 用户画像操作 ==========

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """获取用户画像"""
        try:
            # ✅ 修正: 使用 aget
            result = await self.store.aget(
                namespace=("user_profiles", user_id),
                key="profile"
            )

            if result and result.value:
                return UserProfile(**result.value)

            return UserProfile()

        except Exception as e:
            app_logger.error(f"❌ 获取用户画像失败: {e}")
            return UserProfile()

    async def save_user_profile(self, user_id: str, profile: UserProfile):
        """保存用户画像"""
        profile.updated_at = self._get_current_time()

        # ✅ 修正: 使用 aput
        await self.store.aput(
            namespace=("user_profiles", user_id),
            key="profile",
            value=profile.model_dump()
        )

        app_logger.info(f"保存用户画像: {user_id}")

    async def update_travel_styles(self, user_id: str, styles: List[str]):
        """更新旅行风格偏好"""
        profile = await self.get_user_profile(user_id)
        # 去重并合并
        current_styles = set(profile.travel_styles)
        current_styles.update(styles)
        profile.travel_styles = list(current_styles)

        await self.save_user_profile(user_id, profile)

    async def update_dietary_restrictions(self, user_id: str, restrictions: List[str]):
        """更新饮食禁忌"""
        profile = await self.get_user_profile(user_id)
        current = set(profile.dietary_restrictions)
        current.update(restrictions)
        profile.dietary_restrictions = list(current)

        await self.save_user_profile(user_id, profile)

    async def update_food_preferences(self, user_id: str, preferences: List[str]):
        """更新饮食偏好"""
        profile = await self.get_user_profile(user_id)
        current = set(profile.food_preferences)
        current.update(preferences)
        profile.food_preferences = list(current)

        await self.save_user_profile(user_id, profile)

    # ========== 出行历史操作 ==========

    async def get_travel_history(self, user_id: str) -> TravelHistory:
        """获取出行历史"""
        try:
            # ✅ 修正: 使用 aget
            result = await self.store.aget(
                namespace=("travel_history", user_id),
                key="history"
            )

            if result and result.value:
                return TravelHistory(**result.value)

            return TravelHistory()

        except Exception as e:
            app_logger.error(f"❌ 获取出行历史失败: {e}")
            return TravelHistory()

    async def save_travel_history(self, user_id: str, history: TravelHistory):
        """保存出行历史"""
        history.updated_at = self._get_current_time()

        await self.store.aput(
            namespace=("travel_history", user_id),
            key="history",
            value=history.model_dump()
        )

        app_logger.info(f"保存出行历史: {user_id}")

    async def add_completed_trip(
            self,
            user_id: str,
            destination: str,
            start_date: str,
            end_date: str,
            visited_attractions: List[str]
    ):
        """添加已完成的旅行记录"""
        history = await self.get_travel_history(user_id)

        trip = TravelRecord(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            visited_attractions=visited_attractions
        )
        history.completed_trips.append(trip)

        # 更新去过的景点汇总 (去重)
        current_attractions = set(history.visited_attractions)
        current_attractions.update(visited_attractions)
        history.visited_attractions = list(current_attractions)

        await self.save_travel_history(user_id, history)

        app_logger.info(f"添加旅行记录: {user_id} -> {destination}")

    async def update_accommodation_preference(
            self,
            user_id: str,
            preferred_types: List[str] = None,
            avg_budget: float = None
    ):
        """更新住宿偏好"""
        history = await self.get_travel_history(user_id)

        if preferred_types:
            current_types = set(history.accommodation_preference.preferred_types)
            current_types.update(preferred_types)
            history.accommodation_preference.preferred_types = list(current_types)

        if avg_budget:
            old_budget = history.accommodation_preference.avg_budget_per_night
            if old_budget:
                history.accommodation_preference.avg_budget_per_night = (old_budget + avg_budget) / 2
            else:
                history.accommodation_preference.avg_budget_per_night = avg_budget

        await self.save_travel_history(user_id, history)

        app_logger.info(f"更新住宿偏好: {user_id}")

    async def get_visited_destinations(self, user_id: str) -> List[str]:
        """获取用户去过的所有目的地"""
        history = await self.get_travel_history(user_id)
        return list(set(trip.destination for trip in history.completed_trips))

    async def get_visited_attractions(self, user_id: str) -> List[str]:
        """获取用户去过的所有景点"""
        history = await self.get_travel_history(user_id)
        return history.visited_attractions

    # ========== 搜索操作 (示例，如果后续需要) ==========

    async def search_memories(self, user_id: str, query: str):
        """
        示例：使用 asearch 进行向量相似度搜索
        注意：这需要 Postgres 启用 pgvector 并且 Store 配置了 embedding 模型
        """
        results = await self.store.asearch(
            namespace=("user_profiles", user_id),
            query=query,
            limit=5
        )
        return results

    # ========== 完整记忆操作 ==========

    async def get_user_memory(self, user_id: str) -> UserMemory:
        """获取用户完整的长期记忆"""
        # 这里已经是并行调用了，因为 get_user_profile 和 get_travel_history 内部都 await 了
        # 如果想进一步优化并发，可以使用 asyncio.gather
        profile, history = await asyncio.gather(
            self.get_user_profile(user_id),
            self.get_travel_history(user_id)
        )

        return UserMemory(
            user_id=user_id,
            profile=profile,
            history=history
        )

    async def format_memory_for_prompt(self, user_id: str) -> str:
        """将用户记忆格式化为提示词文本"""
        memory = await self.get_user_memory(user_id)

        parts = ["**用户历史偏好**："]

        # 用户画像
        if memory.profile.travel_styles:
            parts.append(f"- 旅行风格：{', '.join(memory.profile.travel_styles)}")

        if memory.profile.dietary_restrictions:
            parts.append(f"- 饮食禁忌：{', '.join(memory.profile.dietary_restrictions)}")

        if memory.profile.food_preferences:
            parts.append(f"- 饮食偏好：{', '.join(memory.profile.food_preferences)}")

        # 出行历史
        if memory.history.completed_trips:
            # 提取最近去过的目的地
            destinations = list(set(t.destination for t in memory.history.completed_trips))
            parts.append(f"- 去过的目的地：{', '.join(destinations[-5:])}")

        visited_attractions = memory.history.visited_attractions
        if visited_attractions:
            parts.append(f"- 去过的景点：{', '.join(visited_attractions[-10:])}（最近10个）")

        # 住宿偏好
        acc_pref = memory.history.accommodation_preference
        if acc_pref.preferred_types:
            parts.append(f"- 住宿偏好：{', '.join(acc_pref.preferred_types)}")

        if acc_pref.avg_budget_per_night:
            parts.append(f"- 住宿预算：约 {acc_pref.avg_budget_per_night:.0f} 元/晚")

        if len(parts) == 1:
            return ""  # 没有历史数据

        return "\n".join(parts)

# ============== 创建服务实例 ==============

async def get_user_memory_service() -> UserMemoryService:
    """获取用户记忆服务实例"""
    store = await get_store()
    return UserMemoryService(store)