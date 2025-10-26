from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.model.models import ShopCreate
from app.dependencies import get_current_admin
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/admin/shops", tags=["admin-shops"])

@router.post("/{shop_id}/verify")
async def verify_shop_admin(
    shop_id: str,
    current_user: dict = Depends(get_current_admin)
):
    """Admin endpoint to verify a shop"""
    # Check if shop exists
    shop_result = supabase.table("shops").select("*").eq("id", shop_id).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    old_shop_data = shop_result.data[0]
    
    if old_shop_data.get("verified"):
        raise HTTPException(status_code=400, detail="Shop is already verified")
    
    # Update shop verification status
    result = supabase.table("shops").update({"verified": True}).eq("id", shop_id).execute()
    
    # Record shop verification on blockchain
    try:
        verify_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.SHOP_VERIFY,
            user_id=current_user["id"],
            data={
                "shop_id": shop_id,
                "shop_name": old_shop_data.get("name"),
                "previous_status": "unverified",
                "new_status": "verified",
                "action": "shop_verification"
            },
            shop_id=shop_id,
            metadata={
                "source": "admin_shops_route",
                "admin_action": True,
                "verification_timestamp": "immediate"
            }
        )
        
        blockchain_service.add_transaction(verify_transaction)
        
        # Update shop with verification blockchain transaction reference
        supabase.table("shops").update({
            "blockchain_tx_id": verify_transaction.transaction_id
        }).eq("id", shop_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Shop verified successfully",
        "shop_id": shop_id,
        "blockchain_tx_id": verify_transaction.transaction_id if 'verify_transaction' in locals() else None
    }

# Add other admin shop endpoints here if needed
@router.get("/")
async def get_all_shops_admin(
    verified: bool = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(get_current_admin)
):
    """Admin endpoint to get all shops with full details"""
    query = supabase.table("shops").select("*, users(*)", count="exact")
    
    if verified is not None:
        query = query.eq("verified", verified)
    
    result = query.range(offset, offset + limit - 1).execute()
    return {
        "data": result.data,
        "pagination": {
            "total": result.count,
            "offset": offset,
            "limit": limit
        }
    }