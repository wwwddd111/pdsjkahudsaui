"""Async SQLAlchemy models and database operations."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemoCard(Base):
    __tablename__ = 'demo_cards'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id'), index=True)
    gift: Mapped[str] = mapped_column(String(160))
    stars: Mapped[int] = mapped_column(BigInteger)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BusinessLink(Base):
    __tablename__ = 'business_links'
    connection_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Storage:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()

    async def touch(self, user_id: int, username: Optional[str] = None) -> User:
        async with self.sessions() as s:
            user = await s.get(User, user_id)
            if user is None:
                user = User(id=user_id, username=username)
                s.add(user)
            else:
                user.username = username
                user.last_seen = utcnow()
            await s.commit()
            return user

    async def user(self, user_id: int) -> Optional[User]:
        async with self.sessions() as s:
            return await s.get(User, user_id)

    async def set_flag(self, user_id: int, flag: str, value: bool) -> User:
        if flag not in ('approved', 'banned', 'admin'):
            raise ValueError('Unsupported permission flag')
        async with self.sessions() as s:
            user = await s.get(User, user_id)
            if user is None:
                user = User(id=user_id)
                s.add(user)
            setattr(user, flag, value)
            if flag == 'admin' and value:
                user.approved = True
            await s.commit()
            return user

    async def event(self, actor_id: int, kind: str):
        async with self.sessions() as s:
            s.add(Event(actor_id=actor_id, kind=kind))
            await s.commit()

    async def create_card(self, owner_id: int, gift: str, stars: int, photo_file_id: Optional[str] = None) -> DemoCard:
        async with self.sessions() as s:
            card = DemoCard(owner_id=owner_id, gift=gift, stars=stars, photo_file_id=photo_file_id)
            s.add(card)
            await s.commit()
            await s.refresh(card)
            return card

    async def card(self, card_id: int) -> Optional[DemoCard]:
        async with self.sessions() as s:
            return await s.get(DemoCard, card_id)

    async def card_view(self, card_id: int) -> Optional[DemoCard]:
        async with self.sessions() as s:
            card = await s.get(DemoCard, card_id)
            if card:
                card.views += 1
                await s.commit()
            return card

    async def cards_by(self, owner_id: int, limit: int = 10) -> list[DemoCard]:
        async with self.sessions() as s:
            result = await s.scalars(select(DemoCard).where(DemoCard.owner_id == owner_id)
                                     .order_by(DemoCard.id.desc()).limit(limit))
            return list(result)

    async def update_business(self, connection_id: str, owner_id: int, enabled: bool):
        async with self.sessions() as s:
            link = await s.get(BusinessLink, connection_id)
            if link is None:
                link = BusinessLink(connection_id=connection_id, owner_id=owner_id, enabled=enabled)
                s.add(link)
            else:
                link.owner_id = owner_id
                link.enabled = enabled
                link.updated_at = utcnow()
            await s.commit()

    async def business(self, connection_id: str) -> Optional[BusinessLink]:
        async with self.sessions() as s:
            return await s.get(BusinessLink, connection_id)

    async def business_for(self, owner_id: int) -> list[BusinessLink]:
        async with self.sessions() as s:
            return list(await s.scalars(select(BusinessLink).where(BusinessLink.owner_id == owner_id)
                                        .order_by(BusinessLink.updated_at.desc()).limit(10)))

    async def latest_users(self, limit: int = 12) -> list[User]:
        async with self.sessions() as s:
            return list(await s.scalars(select(User).order_by(User.last_seen.desc()).limit(limit)))

    async def stats(self) -> dict[str, int]:
        async with self.sessions() as s:
            async def count(model, *filters):
                q = select(func.count()).select_from(model)
                if filters:
                    q = q.where(*filters)
                return (await s.execute(q)).scalar_one()
            return {
                'users': await count(User),
                'approved': await count(User, User.approved.is_(True)),
                'banned': await count(User, User.banned.is_(True)),
                'admins': await count(User, User.admin.is_(True)),
                'cards': await count(DemoCard),
                'views': (await s.execute(select(func.coalesce(func.sum(DemoCard.views), 0)))).scalar_one(),
                'business': await count(BusinessLink, BusinessLink.enabled.is_(True)),
                'demo_accepts': await count(Event, Event.kind == 'demo_accept'),
                'business_requests': await count(Event, Event.kind == 'business_demo_request'),
            }
