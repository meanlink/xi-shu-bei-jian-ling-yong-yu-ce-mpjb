from pydantic import BaseModel, Field
class StockInput(BaseModel):
    warehouse_id: int
    part: str = Field(min_length=1, max_length=40)
    on_hand: int = Field(ge=0, le=1_000_000_000)
class StockLine(BaseModel):
    warehouse_id: int
    on_hand: int = Field(ge=0, le=1_000_000_000)
class TransferInput(BaseModel):
    job_id: int
    from_warehouse_id: int
    to_warehouse_id: int
    quantity: int = Field(ge=1, le=1_000_000)
    note: str = Field(default='', max_length=200)
    request_id: str = Field(min_length=8, max_length=64)
    stocks: list[StockLine] = Field(default_factory=list)  # 建单时登记双方库房现存量
class QtyInput(BaseModel):
    qty: int = Field(ge=1, le=1_000_000)
    request_id: str = Field(min_length=8, max_length=64)
class RequestIdInput(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
