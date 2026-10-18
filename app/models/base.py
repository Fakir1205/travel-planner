"""
SQLAlchemy 基础配置
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, declared_attr
from datetime import datetime
from app.config import settings

"""
作用：这是所有具体数据库模型（如 User, Order 等）的父类
自动生成表名：通过 __tablename__，当你定义一个名为 UserInfo 的类时，它在数据库里的表名会自动变成 userinfo。
转换为字典：提供了一个 to_dict() 实例方法，方便后续将数据库查询出来的对象直接转换成 JSON 字典返回给前端。
"""


class Base(DeclarativeBase):
    """基础模型类"""

    @declared_attr
    def __tablename__(cls) -> str:
        """自动生成表名（类名转小写）"""
        return cls.__name__.lower()

    def to_dict(self):
        """转换为字典"""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# 创建异步引擎
engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,  # SQL 日志：echo=True 时会在控制台打印所有执行的 SQL 语句，方便在 Debug 模式下排错
    pool_size=10,  # pool_size=10 表示常驻 10 个数据库连接
    max_overflow=20  # 表示在高峰期最多可以额外创建 20 个连接，防止连接数耗尽导致程序崩溃。
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
    # 在同步 SQLAlchemy 中，提交事务后对象会失效（再次访问属性会触发重新查询）；
    # 但在异步环境中，重新查询非常麻烦且容易报错，设为 False 可以保证提交后依然能读取对象里的数据。
)


# 作用：相当于一个“生产数据库会话的流水线”。

# 作用：这是一个非常标准且安全的数据库会话生命周期管理器，
# 主要用于 FastAPI 的依赖注入（Depends(get_db)）。
async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 作用：通常在项目启动时调用。它会检查所有继承自 Base 的模型，如果数据库里没有对应的表，就自动创建出来。