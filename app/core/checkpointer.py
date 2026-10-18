import asyncio
from typing import Optional
from contextlib import asynccontextmanager  #将一个异步生成器函数，转换成一个异步上下文管理器
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.config import settings
from app.utils.logger import app_logger


class CheckpointerManager:
    """Checkpointer 管理器（单例模式）"""

    _instance: Optional['CheckpointerManager'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.pool: Optional[AsyncConnectionPool] = None
        self.checkpointer: Optional[AsyncPostgresSaver] = None

    @classmethod
    async def get_instance(cls) -> 'CheckpointerManager':
        """获取单例实例（线程安全）"""

        # ━━━ 第一重检查（无锁，快速路径）━━━━━━━━━━━━━━━━
        if cls._instance is None:

            # ━━━ 获取锁（只有一个协程能进入）━━━━━━━━━━━
            async with cls._lock:
                # ━━━ 第二重检查（有锁，安全路径）━━━━━━━━━
                if cls._instance is None:
                    cls._instance = cls()        # 创建
                    await cls._instance.initialize() # 初始化
        return cls._instance

    async def initialize(self):
        """初始化连接池和 Checkpointer"""

        # ━━━ 第1步：防御性检查 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if self.checkpointer is not None:
            app_logger.warning("⚠️ Checkpointer 已初始化，跳过")
            return

        try:
            app_logger.info("初始化 PostgreSQL Checkpointer...")

            # 创建异步连接池
            self.pool = AsyncConnectionPool(
                conninfo=settings.database_url,  #  PostgreSQL 连接字符串
                min_size=2,  # 最小连接数
                max_size=20,  # 最大连接数
                #  如何确定这个值？
            #  公式: max_size ≈ PostgreSQL 的 max_connections / 应用实例数
            #  例如: PG max_connections=100, 部署 4 个 Pod → max_size=25
            #  建议留一些余量给管理连接（如监控、迁移）
                timeout=30,  # 连接超时（秒）
                #open=False,
            )

            # 打开连接池
            await self.pool.open()
            #await self.pool.wait()

            # 创建 Checkpointer
            self.checkpointer = AsyncPostgresSaver(self.pool)

            app_logger.info("✅ Checkpointer 初始化完成")

        except Exception as e:
            app_logger.error(f"❌ Checkpointer 初始化失败: {e}")
            raise

    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            app_logger.info("Checkpointer 连接池已关闭")

    def get_checkpointer(self) -> AsyncPostgresSaver:
        """获取 Checkpointer 实例"""
        if self.checkpointer is None:
            raise RuntimeError("Checkpointer 未初始化，请先调用 initialize()")
        return self.checkpointer


# ============== 便捷函数 ==============
async def get_checkpointer() -> AsyncPostgresSaver:
    """
    获取全局 Checkpointer 实例

    用法：
        checkpointer = await get_checkpointer()
        graph = builder.compile(checkpointer=checkpointer)
    """
    manager = await CheckpointerManager.get_instance()
    return manager.get_checkpointer()


@asynccontextmanager
async def checkpointer_lifespan():
    """
    Checkpointer 生命周期管理器（用于 FastAPI lifespan）

    用法：
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with checkpointer_lifespan():
                yield
    """
    manager = await CheckpointerManager.get_instance()
    try:
        yield manager.get_checkpointer()
    finally:
        await manager.close()
