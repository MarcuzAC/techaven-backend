from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.database import supabase
from app.dependencies import get_current_admin
from datetime import datetime, timedelta
from typing import Optional, List

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/metrics")
async def get_admin_metrics(current_user: dict = Depends(get_current_admin)):
    try:
        # Get basic platform metrics
        total_users = supabase.table("users").select("id", count="exact").execute()
        total_shops = supabase.table("shops").select("id", count="exact").execute()
        total_products = supabase.table("products").select("id", count="exact").execute()
        total_orders = supabase.table("orders").select("id", count="exact").execute()
        pending_shops = supabase.table("shops").select("id", count="exact").eq("verified", False).execute()
        
        # Calculate total revenue from orders
        orders_data = supabase.table("orders").select("total_amount").execute()
        total_revenue = sum(order.get('total_amount', 0) for order in (orders_data.data or []))
        
        # Generate monthly data for charts
        monthly_data = generate_monthly_data()
        
        # Calculate growth percentages
        user_growth = calculate_growth(monthly_data, 'users')
        product_growth = calculate_growth(monthly_data, 'products')
        order_growth = calculate_growth(monthly_data, 'orders')
        shop_growth = calculate_growth(monthly_data, 'shops')
        
        # Get blockchain metrics
        blockchain_stats = blockchain_service.get_blockchain_stats()
        total_blockchain_transactions = blockchain_stats["total_transactions"]
        pending_blockchain_transactions = blockchain_stats["pending_transactions"]
        blockchain_valid = blockchain_stats["chain_valid"]
        
        # Get recent blockchain activity for admin dashboard
        recent_blockchain_activity = get_recent_blockchain_activity(limit=10)
        
        # Get transaction type distribution
        transaction_distribution = get_transaction_type_distribution()
        
        return {
            "data": {
                "totalUsers": total_users.count or 0,
                "totalShops": total_shops.count or 0,
                "totalProducts": total_products.count or 0,
                "totalOrders": total_orders.count or 0,
                "totalRevenue": total_revenue,
                "pendingShops": pending_shops.count or 0,
                
                # Blockchain metrics
                "totalBlockchainTransactions": total_blockchain_transactions,
                "pendingBlockchainTransactions": pending_blockchain_transactions,
                "blockchainValid": blockchain_valid,
                "totalBlocks": blockchain_stats["total_blocks"],
                "blockchainDifficulty": blockchain_stats["difficulty"],
                
                # Growth metrics
                "userGrowth": user_growth,
                "productGrowth": product_growth,
                "orderGrowth": order_growth,
                "shopGrowth": shop_growth,
                "revenueGrowth": order_growth,
                
                # Data for charts
                "monthlyData": monthly_data,
                "categoryDistribution": [],
                "blockchainActivity": recent_blockchain_activity,
                "transactionDistribution": transaction_distribution
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching metrics: {str(e)}"
        )

@router.get("/blockchain/stats")
async def get_blockchain_admin_stats(current_user: dict = Depends(get_current_admin)):
    """Get detailed blockchain statistics for admin dashboard"""
    try:
        blockchain_stats = blockchain_service.get_blockchain_stats()
        
        # Get transaction volume by type
        transaction_volume = {}
        for tx_type in TransactionType:
            count = 0
            for block in blockchain_service.blockchain.chain:
                for tx in block.transactions:
                    if tx.transaction_type == tx_type:
                        count += 1
            transaction_volume[tx_type.value] = count
        
        # Get daily transaction volume for the last 7 days
        daily_volume = get_daily_transaction_volume(days=7)
        
        # Get top active users on blockchain
        top_users = get_top_blockchain_users(limit=10)
        
        # Get top active shops on blockchain
        top_shops = get_top_blockchain_shops(limit=10)
        
        return {
            "blockchain_stats": blockchain_stats,
            "transaction_volume_by_type": transaction_volume,
            "daily_transaction_volume": daily_volume,
            "top_active_users": top_users,
            "top_active_shops": top_shops,
            "pending_transactions_count": len(blockchain_service.blockchain.pending_transactions),
            "mining_difficulty": blockchain_service.blockchain.difficulty
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching blockchain stats: {str(e)}"
        )

@router.post("/blockchain/mine")
async def admin_mine_block(current_user: dict = Depends(get_current_admin)):
    """Admin endpoint to manually mine a block"""
    try:
        if not blockchain_service.blockchain.pending_transactions:
            return {
                "message": "No pending transactions to mine",
                "pending_transactions": 0
            }
        
        new_block = blockchain_service.mine_block()
        
        # Record admin mining activity on blockchain
        try:
            mine_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_REGISTER,  # Using existing type
                user_id=current_user["id"],
                data={
                    "action": "admin_block_mining",
                    "block_index": new_block.index,
                    "transactions_mined": len(new_block.transactions),
                    "proof": new_block.proof,
                    "mining_difficulty": blockchain_service.blockchain.difficulty
                },
                metadata={
                    "source": "admin_route",
                    "admin_action": True,
                    "manual_mining": True
                }
            )
            
            blockchain_service.add_transaction(mine_transaction)
            
        except Exception as e:
            print(f"Blockchain mining transaction failed: {e}")
        
        return {
            "message": "Block mined successfully by admin",
            "block": {
                "index": new_block.index,
                "timestamp": new_block.timestamp,
                "transactions_count": len(new_block.transactions),
                "proof": new_block.proof,
                "hash": new_block.hash,
                "previous_hash": new_block.previous_hash
            },
            "miner": {
                "admin_id": current_user["id"],
                "admin_email": current_user["email"]
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error mining block: {str(e)}"
        )

@router.get("/blockchain/transactions")
async def get_blockchain_transactions_admin(
    current_user: dict = Depends(get_current_admin),
    transaction_type: Optional[TransactionType] = None,
    user_id: Optional[str] = None,
    shop_id: Optional[str] = None,
    product_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = 0
):
    """Admin endpoint to search and filter blockchain transactions"""
    try:
        all_transactions = []
        
        # Get transactions from mined blocks
        for block in blockchain_service.blockchain.chain[offset:offset + limit]:
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
                    "transaction_type": tx.transaction_type.value,
                    "user_id": tx.user_id,
                    "timestamp": tx.timestamp,
                    "data": tx.data,
                    "metadata": tx.metadata,
                    "block_index": block.index,
                    "confirmed": True,
                    "shop_id": tx.shop_id,
                    "product_id": tx.product_id,
                    "order_id": tx.order_id,
                    "promotion_id": tx.promotion_id
                })
        
        # Get pending transactions that match criteria
        pending_count = 0
        for tx in blockchain_service.blockchain.pending_transactions:
            if len(all_transactions) >= limit:
                break
                
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
                "transaction_type": tx.transaction_type.value,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "metadata": tx.metadata,
                "block_index": None,
                "confirmed": False,
                "shop_id": tx.shop_id,
                "product_id": tx.product_id,
                "order_id": tx.order_id,
                "promotion_id": tx.promotion_id
            })
            pending_count += 1
        
        return {
            "total_transactions": len(all_transactions),
            "confirmed_transactions": len(all_transactions) - pending_count,
            "pending_transactions": pending_count,
            "transactions": sorted(all_transactions, key=lambda x: x["timestamp"], reverse=True)[:limit]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching blockchain transactions: {str(e)}"
        )

@router.get("/blockchain/validity")
async def check_blockchain_validity(current_user: dict = Depends(get_current_admin)):
    """Admin endpoint to thoroughly check blockchain validity"""
    try:
        is_valid = blockchain_service.is_chain_valid()
        issues = []
        
        if not is_valid:
            # Perform detailed validation to identify issues
            issues = validate_blockchain_detailed()
        
        blockchain_stats = blockchain_service.get_blockchain_stats()
        
        return {
            "is_valid": is_valid,
            "total_blocks": blockchain_stats["total_blocks"],
            "total_transactions": blockchain_stats["total_transactions"],
            "pending_transactions": blockchain_stats["pending_transactions"],
            "validation_issues": issues,
            "last_validation_check": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error validating blockchain: {str(e)}"
        )

@router.post("/blockchain/difficulty")
async def update_mining_difficulty(
    difficulty: int = Query(..., ge=1, le=10, description="Mining difficulty (1-10)"),
    current_user: dict = Depends(get_current_admin)
):
    """Admin endpoint to update mining difficulty"""
    try:
        old_difficulty = blockchain_service.blockchain.difficulty
        blockchain_service.blockchain.difficulty = difficulty
        
        # Record difficulty change on blockchain
        try:
            difficulty_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_REGISTER,  # Using existing type
                user_id=current_user["id"],
                data={
                    "action": "mining_difficulty_update",
                    "previous_difficulty": old_difficulty,
                    "new_difficulty": difficulty,
                    "change_reason": "admin_manual_adjustment"
                },
                metadata={
                    "source": "admin_route",
                    "admin_action": True,
                    "system_parameter_change": True
                }
            )
            
            blockchain_service.add_transaction(difficulty_transaction)
            
        except Exception as e:
            print(f"Blockchain difficulty transaction failed: {e}")
        
        return {
            "message": "Mining difficulty updated successfully",
            "previous_difficulty": old_difficulty,
            "new_difficulty": difficulty,
            "blockchain_tx_id": difficulty_transaction.transaction_id if 'difficulty_transaction' in locals() else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error updating mining difficulty: {str(e)}"
        )

# Helper functions
def generate_monthly_data():
    """Generate monthly data for the last 6 months"""
    monthly_data = []
    current_date = datetime.now()
    
    # Generate data for last 6 months
    for i in range(5, -1, -1):
        month_date = current_date - timedelta(days=30*i)
        month_name = month_date.strftime("%b")
        
        # Calculate start and end of the month
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(seconds=1)
        
        # Get users created in this month
        users_result = supabase.table("users").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get products created in this month
        products_result = supabase.table("products").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get orders created in this month
        orders_result = supabase.table("orders").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get shops created in this month
        shops_result = supabase.table("shops").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        monthly_data.append({
            "name": month_name,
            "users": users_result.count or 0,
            "products": products_result.count or 0,
            "orders": orders_result.count or 0,
            "shops": shops_result.count or 0
        })
    
    return monthly_data

def calculate_growth(monthly_data, metric):
    """Calculate growth percentage for the last month compared to previous month"""
    if len(monthly_data) < 2:
        return 0
    
    current_month = monthly_data[-1].get(metric, 0)
    previous_month = monthly_data[-2].get(metric, 0)
    
    if previous_month == 0:
        return 100 if current_month > 0 else 0
    
    growth = ((current_month - previous_month) / previous_month) * 100
    return round(growth, 1)

def get_recent_blockchain_activity(limit: int = 10):
    """Get recent blockchain activity for admin dashboard"""
    recent_activity = []
    
    # Get recent transactions from the latest blocks
    for block in reversed(blockchain_service.blockchain.chain[-3:]):  # Last 3 blocks
        for tx in block.transactions:
            if len(recent_activity) >= limit:
                break
            recent_activity.append({
                "transaction_type": tx.transaction_type.value,
                "timestamp": tx.timestamp,
                "user_id": tx.user_id,
                "data_summary": {k: v for k, v in tx.data.items() if k in ['action', 'product_title', 'shop_name', 'order_id']}
            })
    
    return recent_activity

def get_transaction_type_distribution():
    """Get distribution of transaction types for analytics"""
    distribution = {}
    
    for block in blockchain_service.blockchain.chain:
        for tx in block.transactions:
            tx_type = tx.transaction_type.value
            distribution[tx_type] = distribution.get(tx_type, 0) + 1
    
    return distribution

def get_daily_transaction_volume(days: int = 7):
    """Get daily transaction volume for the last N days"""
    daily_volume = []
    current_date = datetime.now()
    
    for i in range(days - 1, -1, -1):
        date = current_date - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        
        # Count transactions for this date
        count = 0
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                if tx.timestamp.date() == date.date():
                    count += 1
        
        daily_volume.append({
            "date": date_str,
            "transactions": count
        })
    
    return daily_volume

def get_top_blockchain_users(limit: int = 10):
    """Get top users by blockchain activity"""
    user_activity = {}
    
    for block in blockchain_service.blockchain.chain:
        for tx in block.transactions:
            user_id = tx.user_id
            user_activity[user_id] = user_activity.get(user_id, 0) + 1
    
    # Sort by activity count
    sorted_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)
    
    # Get user details for top users
    top_users = []
    for user_id, count in sorted_users[:limit]:
        user_result = supabase.table("users").select("name, email, type").eq("id", user_id).execute()
        if user_result.data:
            user = user_result.data[0]
            top_users.append({
                "user_id": user_id,
                "name": user["name"],
                "email": user["email"],
                "type": user["type"],
                "transaction_count": count
            })
    
    return top_users

def get_top_blockchain_shops(limit: int = 10):
    """Get top shops by blockchain activity"""
    shop_activity = {}
    
    for block in blockchain_service.blockchain.chain:
        for tx in block.transactions:
            if tx.shop_id:
                shop_activity[tx.shop_id] = shop_activity.get(tx.shop_id, 0) + 1
    
    # Sort by activity count
    sorted_shops = sorted(shop_activity.items(), key=lambda x: x[1], reverse=True)
    
    # Get shop details for top shops
    top_shops = []
    for shop_id, count in sorted_shops[:limit]:
        shop_result = supabase.table("shops").select("name, verified").eq("id", shop_id).execute()
        if shop_result.data:
            shop = shop_result.data[0]
            top_shops.append({
                "shop_id": shop_id,
                "name": shop["name"],
                "verified": shop["verified"],
                "transaction_count": count
            })
    
    return top_shops

def validate_blockchain_detailed():
    """Perform detailed blockchain validation to identify specific issues"""
    issues = []
    
    if len(blockchain_service.blockchain.chain) == 0:
        issues.append("Blockchain is empty")
        return issues
    
    # Check genesis block
    genesis_block = blockchain_service.blockchain.chain[0]
    if genesis_block.index != 0:
        issues.append(f"Genesis block has invalid index: {genesis_block.index}")
    
    if genesis_block.previous_hash != "0" * 64:
        issues.append("Genesis block has invalid previous hash")
    
    # Check each block
    for i in range(1, len(blockchain_service.blockchain.chain)):
        current_block = blockchain_service.blockchain.chain[i]
        previous_block = blockchain_service.blockchain.chain[i-1]
        
        # Check hash integrity
        calculated_hash = blockchain_service.calculate_hash(current_block)
        if current_block.hash != calculated_hash:
            issues.append(f"Block {i} has invalid hash")
        
        # Check chain linkage
        if current_block.previous_hash != previous_block.hash:
            issues.append(f"Block {i} has invalid previous hash reference")
        
        # Check proof of work
        if not blockchain_service.valid_proof(previous_block.proof, current_block.proof):
            issues.append(f"Block {i} has invalid proof of work")
    
    return issues