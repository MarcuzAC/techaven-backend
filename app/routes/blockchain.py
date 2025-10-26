from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.dependencies import get_current_user
from app.blockchain.service import blockchain_service
from app.blockchain.models import (
    BlockchainTransactionResponse, 
    BlockResponse, 
    ChainValidationResponse,
    BlockchainStatsResponse,
    TransactionType
)

router = APIRouter(prefix="/blockchain", tags=["blockchain"])

@router.get("/chain", response_model=Dict[str, Any])
async def get_full_chain():
    """Get the entire blockchain"""
    try:
        chain_data = {
            "chain": [
                {
                    "index": block.index,
                    "timestamp": block.timestamp,
                    "transactions": [
                        {
                            "transaction_id": tx.transaction_id,
                            "transaction_type": tx.transaction_type,
                            "user_id": tx.user_id,
                            "timestamp": tx.timestamp,
                            "data": tx.data,
                            "shop_id": tx.shop_id,
                            "product_id": tx.product_id,
                            "order_id": tx.order_id
                        }
                        for tx in block.transactions
                    ],
                    "proof": block.proof,
                    "previous_hash": block.previous_hash,
                    "hash": block.hash
                }
                for block in blockchain_service.blockchain.chain
            ],
            "length": len(blockchain_service.blockchain.chain)
        }
        return chain_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chain: {str(e)}")

@router.get("/blocks/latest", response_model=BlockResponse)
async def get_latest_block():
    """Get the latest block in the chain"""
    try:
        last_block = blockchain_service.get_last_block()
        return {
            "index": last_block.index,
            "timestamp": last_block.timestamp,
            "transactions_count": len(last_block.transactions),
            "proof": last_block.proof,
            "previous_hash": last_block.previous_hash,
            "hash": last_block.hash
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve latest block: {str(e)}")

@router.get("/blocks/{index}", response_model=BlockResponse)
async def get_block_by_index(index: int):
    """Get a specific block by index"""
    try:
        if index < 0 or index >= len(blockchain_service.blockchain.chain):
            raise HTTPException(status_code=404, detail="Block not found")
        
        block = blockchain_service.blockchain.chain[index]
        return {
            "index": block.index,
            "timestamp": block.timestamp,
            "transactions_count": len(block.transactions),
            "proof": block.proof,
            "previous_hash": block.previous_hash,
            "hash": block.hash
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve block: {str(e)}")

@router.post("/mine", response_model=Dict[str, Any])
async def mine_block(current_user: dict = Depends(get_current_user)):
    """Manually mine a new block with pending transactions"""
    try:
        if not blockchain_service.blockchain.pending_transactions:
            return {
                "message": "No pending transactions to mine",
                "pending_transactions": 0
            }
        
        new_block = blockchain_service.mine_block()
        
        return {
            "message": "New block mined successfully!",
            "block": {
                "index": new_block.index,
                "timestamp": new_block.timestamp,
                "transactions_count": len(new_block.transactions),
                "proof": new_block.proof,
                "previous_hash": new_block.previous_hash,
                "hash": new_block.hash
            },
            "miner": {
                "user_id": current_user["id"],
                "email": current_user["email"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mine block: {str(e)}")

@router.get("/transactions/pending", response_model=List[BlockchainTransactionResponse])
async def get_pending_transactions():
    """Get all pending transactions"""
    try:
        pending_txs = []
        for tx in blockchain_service.blockchain.pending_transactions:
            pending_txs.append({
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "block_index": None,
                "confirmed": False
            })
        return pending_txs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve pending transactions: {str(e)}")

@router.get("/transactions/user/{user_id}", response_model=List[BlockchainTransactionResponse])
async def get_user_transactions(user_id: str):
    """Get all transactions for a specific user"""
    try:
        transactions = blockchain_service.get_transactions_by_user(user_id)
        return [
            {
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "block_index": next(
                    (i for i, block in enumerate(blockchain_service.blockchain.chain) 
                     if tx in block.transactions), None
                ),
                "confirmed": any(tx in block.transactions for block in blockchain_service.blockchain.chain)
            }
            for tx in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve user transactions: {str(e)}")

@router.get("/transactions/shop/{shop_id}", response_model=List[BlockchainTransactionResponse])
async def get_shop_transactions(shop_id: str):
    """Get all transactions for a specific shop"""
    try:
        transactions = blockchain_service.get_transactions_by_shop(shop_id)
        return [
            {
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "block_index": next(
                    (i for i, block in enumerate(blockchain_service.blockchain.chain) 
                     if tx in block.transactions), None
                ),
                "confirmed": any(tx in block.transactions for block in blockchain_service.blockchain.chain)
            }
            for tx in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve shop transactions: {str(e)}")

@router.get("/transactions/product/{product_id}", response_model=List[BlockchainTransactionResponse])
async def get_product_transactions(product_id: str):
    """Get all transactions for a specific product"""
    try:
        transactions = blockchain_service.get_transactions_by_product(product_id)
        return [
            {
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "block_index": next(
                    (i for i, block in enumerate(blockchain_service.blockchain.chain) 
                     if tx in block.transactions), None
                ),
                "confirmed": any(tx in block.transactions for block in blockchain_service.blockchain.chain)
            }
            for tx in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve product transactions: {str(e)}")

@router.get("/valid", response_model=ChainValidationResponse)
async def validate_chain():
    """Validate the entire blockchain"""
    try:
        is_valid = blockchain_service.is_chain_valid()
        total_transactions = sum(len(block.transactions) for block in blockchain_service.blockchain.chain)
        
        return {
            "is_valid": is_valid,
            "total_blocks": len(blockchain_service.blockchain.chain),
            "total_transactions": total_transactions,
            "issues": [] if is_valid else ["Chain validation failed - check block integrity"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate chain: {str(e)}")

@router.get("/stats", response_model=BlockchainStatsResponse)
async def get_blockchain_stats():
    """Get blockchain statistics"""
    try:
        stats = blockchain_service.get_blockchain_stats()
        return BlockchainStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve blockchain stats: {str(e)}")

@router.get("/search/transactions")
async def search_transactions(
    transaction_type: TransactionType = None,
    user_id: str = None,
    shop_id: str = None,
    product_id: str = None
):
    """Search transactions by various criteria"""
    try:
        all_transactions = []
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                # Apply filters
                if transaction_type and tx.transaction_type != transaction_type:
                    continue
                if user_id and tx.user_id != user_id:
                    continue
                if shop_id and tx.shop_id != shop_id:
                    continue
                if product_id and tx.product_id != product_id:
                    continue
                
                all_transactions.append({
                    "transaction_id": tx.transaction_id,
                    "transaction_type": tx.transaction_type,
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp,
                    "data": tx.data,
                    "shop_id": tx.shop_id,
                    "product_id": tx.product_id,
                    "order_id": tx.order_id,
                    "block_index": block.index,
                    "confirmed": True
                })
        
        # Also include pending transactions that match criteria
        for tx in blockchain_service.blockchain.pending_transactions:
            if transaction_type and tx.transaction_type != transaction_type:
                continue
            if user_id and tx.user_id != user_id:
                continue
            if shop_id and tx.shop_id != shop_id:
                continue
            if product_id and tx.product_id != product_id:
                continue
            
            all_transactions.append({
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "shop_id": tx.shop_id,
                "product_id": tx.product_id,
                "order_id": tx.order_id,
                "block_index": None,
                "confirmed": False
            })
        
        return {
            "total_results": len(all_transactions),
            "transactions": sorted(all_transactions, key=lambda x: x["timestamp"], reverse=True)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search transactions: {str(e)}")