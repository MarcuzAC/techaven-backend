from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class TransactionType(str, Enum):
    USER_REGISTER = "user_register"
    SHOP_CREATE = "shop_create"
    SHOP_VERIFY = "shop_verify"
    PRODUCT_CREATE = "product_create"
    PRODUCT_UPDATE = "product_update"
    PRODUCT_DELETE = "product_delete"
    ORDER_CREATE = "order_create"
    ORDER_UPDATE = "order_update"
    ORDER_CANCEL = "order_cancel"
    PROMOTION_CREATE = "promotion_create"
    PROMOTION_UPDATE = "promotion_update"
    REVIEW_CREATE = "review_create"
    PRICE_UPDATE = "price_update"
    STOCK_UPDATE = "stock_update"

class BlockchainTransaction(BaseModel):
    transaction_id: str
    transaction_type: TransactionType
    user_id: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Optional references for different entity types
    shop_id: Optional[str] = None
    product_id: Optional[str] = None
    order_id: Optional[str] = None
    promotion_id: Optional[str] = None

class Block(BaseModel):
    index: int
    timestamp: datetime
    transactions: List[BlockchainTransaction]
    proof: int
    previous_hash: str
    hash: Optional[str] = None

class Blockchain(BaseModel):
    chain: List[Block] = Field(default_factory=list)
    pending_transactions: List[BlockchainTransaction] = Field(default_factory=list)
    difficulty: int = 4

# Blockchain-specific responses
class BlockchainTransactionResponse(BaseModel):
    transaction_id: str
    transaction_type: str
    user_id: str
    timestamp: datetime
    data: Dict[str, Any]
    block_index: Optional[int] = None
    confirmed: bool = False

class BlockResponse(BaseModel):
    index: int
    timestamp: datetime
    transactions_count: int
    proof: int
    previous_hash: str
    hash: str

class ChainValidationResponse(BaseModel):
    is_valid: bool
    total_blocks: int
    total_transactions: int
    issues: List[str] = Field(default_factory=list)

class BlockchainStatsResponse(BaseModel):
    total_blocks: int
    total_transactions: int
    pending_transactions: int
    chain_valid: bool
    last_block_timestamp: Optional[datetime]
    difficulty: int