from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.model.models import PromotionCreate, PromotionResponse
from app.dependencies import get_current_merchant, get_current_admin, get_current_user

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/promotions", tags=["promotions"])

@router.post("/", response_model=dict)
async def create_promotion(promo_data: PromotionCreate, current_user: dict = Depends(get_current_merchant)):
    # Get user's shop
    shop_result = supabase.table("shops").select("id, name").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    shop_name = shop_result.data[0]["name"]
    promo_dict = promo_data.dict()
    promo_dict["shop_id"] = shop_id
    promo_dict["status"] = "pending"  # Needs admin approval
    
    # Verify product belongs to shop if specified
    product_name = None
    if promo_dict["product_id"]:
        product_result = supabase.table("products").select("id, title, shop_id").eq("id", promo_dict["product_id"]).execute()
        if not product_result.data or product_result.data[0]["shop_id"] != shop_id:
            raise HTTPException(status_code=400, detail="Product not found or doesn't belong to your shop")
        product_name = product_result.data[0]["title"]
    
    result = supabase.table("promotions").insert(promo_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create promotion"
        )
    
    promotion_id = result.data[0]["id"]
    
    # Record promotion creation on blockchain
    try:
        promotion_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PROMOTION_CREATE,
            user_id=current_user["id"],
            data={
                "promotion_id": promotion_id,
                "promotion_type": promo_data.type,
                "shop_id": shop_id,
                "shop_name": shop_name,
                "budget": promo_data.budget,
                "start_date": promo_data.start_date.isoformat(),
                "end_date": promo_data.end_date.isoformat(),
                "product_id": promo_data.product_id,
                "product_name": product_name,
                "status": "pending",
                "action": "promotion_creation"
            },
            shop_id=shop_id,
            product_id=promo_data.product_id,
            promotion_id=promotion_id,
            metadata={
                "source": "promotions_route",
                "requires_approval": True,
                "budget_allocated": promo_data.budget
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(promotion_transaction)
        
        # Update promotion with blockchain transaction reference
        supabase.table("promotions").update({
            "blockchain_tx_id": promotion_transaction.transaction_id
        }).eq("id", promotion_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with promotion creation even if blockchain fails
    
    return {
        "message": "Promotion created successfully", 
        "promotion_id": promotion_id,
        "status": "pending",
        "blockchain_tx_id": promotion_transaction.transaction_id if 'promotion_transaction' in locals() else None
    }

@router.get("/")
async def get_shop_promotions(current_user: dict = Depends(get_current_merchant)):
    shop_result = supabase.table("shops").select("id, name").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    result = supabase.table("promotions").select("*, products(title)").eq("shop_id", shop_id).execute()
    
    # Enhance with blockchain data
    promotions_with_blockchain = []
    for promotion in result.data:
        try:
            # Get blockchain transactions for this promotion
            promotion_transactions = blockchain_service.get_transactions_by_product(promotion.get("product_id", ""))
            promotion["blockchain_activity_count"] = len([
                tx for tx in promotion_transactions 
                if tx.promotion_id == promotion["id"]
            ])
        except Exception as e:
            print(f"Failed to get blockchain data for promotion {promotion['id']}: {e}")
            promotion["blockchain_activity_count"] = 0
        
        promotions_with_blockchain.append(promotion)
    
    return promotions_with_blockchain

@router.get("/all")
async def get_all_promotions(
    status: str = None,
    shop_id: str = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_admin)
):
    """Admin endpoint to get all promotions"""
    query = supabase.table("promotions").select("*, shops(name), products(title)", count="exact")
    
    if status:
        query = query.eq("status", status)
    
    if shop_id:
        query = query.eq("shop_id", shop_id)
    
    result = query.range(offset, offset + limit - 1).execute()
    
    # Enhance with blockchain data
    promotions_with_blockchain = []
    for promotion in result.data:
        try:
            # Get blockchain transactions for this promotion
            promotion_transactions = [
                tx for tx in blockchain_service.get_transactions_by_product(promotion.get("product_id", ""))
                if tx.promotion_id == promotion["id"]
            ]
            promotion["blockchain_activity"] = {
                "total_transactions": len(promotion_transactions),
                "recent_activity": [
                    {
                        "transaction_type": tx.transaction_type,
                        "timestamp": tx.timestamp,
                        "user_id": tx.user_id
                    }
                    for tx in promotion_transactions[:3]
                ]
            }
        except Exception as e:
            print(f"Failed to get blockchain data for promotion {promotion['id']}: {e}")
            promotion["blockchain_activity"] = {"total_transactions": 0, "recent_activity": []}
        
        promotions_with_blockchain.append(promotion)
    
    return {
        "data": promotions_with_blockchain,
        "pagination": {
            "total": result.count,
            "offset": offset,
            "limit": limit
        }
    }

@router.put("/admin/{promotion_id}/status")
async def update_promotion_status(
    promotion_id: str,
    status: str,
    current_user: dict = Depends(get_current_admin)
):
    """Admin endpoint to update promotion status (approve/reject)"""
    # Check if promotion exists
    promotion_result = supabase.table("promotions").select("*, shops(name, user_id), products(title)").eq("id", promotion_id).execute()
    if not promotion_result.data:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    promotion = promotion_result.data[0]
    old_status = promotion["status"]
    
    if old_status == status:
        raise HTTPException(status_code=400, detail=f"Promotion is already {status}")
    
    # Update promotion status
    result = supabase.table("promotions").update({"status": status}).eq("id", promotion_id).execute()
    
    # Record promotion status update on blockchain
    try:
        status_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PROMOTION_UPDATE,
            user_id=current_user["id"],
            data={
                "promotion_id": promotion_id,
                "promotion_type": promotion["type"],
                "shop_id": promotion["shop_id"],
                "shop_name": promotion["shops"]["name"],
                "product_id": promotion["product_id"],
                "product_name": promotion["products"]["title"] if promotion["products"] else None,
                "previous_status": old_status,
                "new_status": status,
                "budget": promotion["budget"],
                "action": "promotion_status_update"
            },
            shop_id=promotion["shop_id"],
            product_id=promotion["product_id"],
            promotion_id=promotion_id,
            metadata={
                "source": "promotions_route_admin",
                "admin_action": True,
                "status_change": f"{old_status}->{status}"
            }
        )
        
        blockchain_service.add_transaction(status_transaction)
        
        # Update promotion with new blockchain transaction reference
        supabase.table("promotions").update({
            "blockchain_tx_id": status_transaction.transaction_id
        }).eq("id", promotion_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": f"Promotion status updated to {status}",
        "promotion_id": promotion_id,
        "previous_status": old_status,
        "new_status": status,
        "blockchain_tx_id": status_transaction.transaction_id if 'status_transaction' in locals() else None
    }

@router.put("/{promotion_id}")
async def update_promotion(
    promotion_id: str,
    promo_data: PromotionCreate,
    current_user: dict = Depends(get_current_merchant)
):
    """Update promotion details"""
    # Check if promotion exists and belongs to user's shop
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    
    promotion_result = supabase.table("promotions").select("*").eq("id", promotion_id).eq("shop_id", shop_id).execute()
    if not promotion_result.data:
        raise HTTPException(status_code=404, detail="Promotion not found or access denied")
    
    old_promotion = promotion_result.data[0]
    
    # Verify product belongs to shop if specified
    if promo_data.product_id:
        product_result = supabase.table("products").select("shop_id").eq("id", promo_data.product_id).execute()
        if not product_result.data or product_result.data[0]["shop_id"] != shop_id:
            raise HTTPException(status_code=400, detail="Product not found or doesn't belong to your shop")
    
    # Update promotion
    update_data = promo_data.dict()
    update_data["status"] = "pending"  # Reset to pending when updated
    
    result = supabase.table("promotions").update(update_data).eq("id", promotion_id).execute()
    
    # Record promotion update on blockchain
    try:
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PROMOTION_UPDATE,
            user_id=current_user["id"],
            data={
                "promotion_id": promotion_id,
                "promotion_type": promo_data.type,
                "shop_id": shop_id,
                "updated_fields": list(promo_data.dict().keys()),
                "previous_data": {
                    "type": old_promotion["type"],
                    "budget": old_promotion["budget"],
                    "start_date": old_promotion["start_date"],
                    "end_date": old_promotion["end_date"],
                    "product_id": old_promotion["product_id"]
                },
                "new_data": update_data,
                "action": "promotion_update"
            },
            shop_id=shop_id,
            product_id=promo_data.product_id,
            promotion_id=promotion_id,
            metadata={
                "source": "promotions_route",
                "requires_reapproval": True
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Promotion updated successfully",
        "promotion_id": promotion_id,
        "status": "pending",
        "blockchain_tx_id": update_transaction.transaction_id if 'update_transaction' in locals() else None
    }

@router.get("/{promotion_id}/blockchain-activity")
async def get_promotion_blockchain_activity(
    promotion_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get blockchain activity for a specific promotion"""
    try:
        # Check if promotion exists
        promotion_result = supabase.table("promotions").select("*, shops(name)").eq("id", promotion_id).execute()
        if not promotion_result.data:
            raise HTTPException(status_code=404, detail="Promotion not found")
        
        promotion = promotion_result.data[0]
        
        # Check access rights
        if current_user["type"] == "merchant":
            shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
            if not shop_result.data or shop_result.data[0]["id"] != promotion["shop_id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        
        # Get all transactions for this promotion
        all_transactions = []
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                if tx.promotion_id == promotion_id:
                    all_transactions.append(tx)
        
        # Also check pending transactions
        for tx in blockchain_service.blockchain.pending_transactions:
            if tx.promotion_id == promotion_id:
                all_transactions.append(tx)
        
        # Format response
        activity = []
        for tx in all_transactions:
            # Determine if transaction is confirmed (in a block)
            confirmed = any(
                tx in block.transactions 
                for block in blockchain_service.blockchain.chain
            )
            
            # Find block index if confirmed
            block_index = None
            if confirmed:
                for i, block in enumerate(blockchain_service.blockchain.chain):
                    if tx in block.transactions:
                        block_index = i
                        break
            
            activity.append({
                "transaction_id": tx.transaction_id,
                "transaction_type": tx.transaction_type.value,
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "metadata": tx.metadata,
                "confirmed": confirmed,
                "block_index": block_index
            })
        
        return {
            "promotion_id": promotion_id,
            "promotion_type": promotion["type"],
            "shop_name": promotion["shops"]["name"],
            "status": promotion["status"],
            "total_activities": len(activity),
            "activity": sorted(activity, key=lambda x: x["timestamp"], reverse=True)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve blockchain activity: {str(e)}"
        )

@router.delete("/{promotion_id}")
async def delete_promotion(
    promotion_id: str,
    current_user: dict = Depends(get_current_merchant)
):
    """Delete a promotion"""
    # Check if promotion exists and belongs to user's shop
    shop_result = supabase.table("shops").select("id, name").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    shop_name = shop_result.data[0]["name"]
    
    promotion_result = supabase.table("promotions").select("*").eq("id", promotion_id).eq("shop_id", shop_id).execute()
    if not promotion_result.data:
        raise HTTPException(status_code=404, detail="Promotion not found or access denied")
    
    promotion = promotion_result.data[0]
    
    # Record promotion deletion on blockchain
    try:
        delete_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PROMOTION_UPDATE,  # Using update type or create PROMOTION_DELETE
            user_id=current_user["id"],
            data={
                "promotion_id": promotion_id,
                "promotion_type": promotion["type"],
                "shop_id": shop_id,
                "shop_name": shop_name,
                "budget": promotion["budget"],
                "action": "promotion_deletion"
            },
            shop_id=shop_id,
            product_id=promotion["product_id"],
            promotion_id=promotion_id,
            metadata={
                "source": "promotions_route",
                "permanent_deletion": True
            }
        )
        
        blockchain_service.add_transaction(delete_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    # Delete the promotion
    result = supabase.table("promotions").delete().eq("id", promotion_id).execute()
    
    return {
        "message": "Promotion deleted successfully",
        "promotion_id": promotion_id,
        "blockchain_tx_id": delete_transaction.transaction_id if 'delete_transaction' in locals() else None
    }