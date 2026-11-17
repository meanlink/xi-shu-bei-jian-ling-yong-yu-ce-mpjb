from sqlalchemy import String, Double, Integer, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Warehouse(Base):
    __tablename__ = 'warehouses'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
class StockBalance(Base):
    __tablename__ = 'stock_balances'
    __table_args__ = (UniqueConstraint('warehouse_id', 'part'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouses.id'))
    part: Mapped[str] = mapped_column(String(40))
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Double)
class Transfer(Base):
    __tablename__ = 'transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    client_ref: Mapped[str] = mapped_column(String(64), unique=True)  # 建单幂等键
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))  # 只读引用已批准预测，不回写
    part: Mapped[str] = mapped_column(String(40))
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouses.id'))
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouses.id'))
    quantity: Mapped[int] = mapped_column(Integer)  # 计划调拨量
    shipped_qty: Mapped[int] = mapped_column(Integer, default=0)
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    recalled_qty: Mapped[int] = mapped_column(Integer, default=0)  # 已撤回（退运在途+已退回）
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)  # 原库已确认退回
    status: Mapped[str] = mapped_column(String(20), default='pending')
    note: Mapped[str] = mapped_column(String(200), default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    updated_at: Mapped[float] = mapped_column(Double)
class TransferEvent(Base):
    __tablename__ = 'transfer_events'
    __table_args__ = (UniqueConstraint('transfer_id', 'request_id'),)  # 操作幂等：重试不重复落账
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('transfers.id'))
    kind: Mapped[str] = mapped_column(String(20))  # create/ship/receive/recall/return
    qty: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(150))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # 落账后两库可用量与在途量
    at: Mapped[float] = mapped_column(Double)
