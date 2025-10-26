from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.model.models import ShopCreate, ShopResponse
from app.dependencies import get_current_merchant, get_current_user, get_current_admin

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/shops", tags=["shops"])

@router.post("/", response_model=dict)
async def create_shop(shop_data: ShopCreate, current_user: dict = Depends(get_current_merchant)):
    # Check if user already has a shop
    existing_shop = supabase.table("shops").select("*").eq("user_id", current_user["id"]).execute()
    if existing_shop.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a shop"
        )
    
    shop_data_dict = shop_data.dict()
    shop_data_dict["user_id"] = current_user["id"]
    shop_data_dict["verified"] = False
    shop_data_dict["rating"] = 0.0  # Default rating
    
    result = supabase.table("shops").insert(shop_data_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shop"
        )
    
    shop_id = result.data[0]["id"]
    
    # Record shop creation on blockchain
    try:
        shop_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.SHOP_CREATE,
            user_id=current_user["id"],
            data={
                "shop_name": shop_data.name,
                "shop_id": shop_id,
                "description": shop_data.description,
                "address": shop_data.address,
                "phone": shop_data.phone,
                "verified": False,
                "action": "shop_creation"
            },
            shop_id=shop_id,
            metadata={
                "source": "shops_route",
                "user_initiated": True
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(shop_transaction)
        
        # Update shop with blockchain transaction reference
        supabase.table("shops").update({
            "blockchain_tx_id": shop_transaction.transaction_id
        }).eq("id", shop_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with shop creation even if blockchain fails
    
    return {
        "message": "Shop created successfully", 
        "shop_id": shop_id,
        "blockchain_tx_id": shop_transaction.transaction_id if 'shop_transaction' in locals() else None
    }

@router.post("/admin/create", response_model=dict)
async def create_shop_admin(
    shop_data: ShopCreate, 
    user_id: str = None,
    verified: bool = True,
    current_user: dict = Depends(get_current_admin)
):
    """
    Admin endpoint to create a shop for any user
    """
    # If no user_id provided, create shop for the admin themselves
    target_user_id = user_id or current_user["id"]
    
    # Check if user already has a shop (unless it's the admin creating for themselves)
    if not user_id:
        existing_shop = supabase.table("shops").select("*").eq("user_id", target_user_id).execute()
        if existing_shop.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has a shop"
            )
    
    shop_data_dict = shop_data.dict()
    shop_data_dict["user_id"] = target_user_id
    shop_data_dict["verified"] = verified
    shop_data_dict["rating"] = 0.0  # Default rating
    
    result = supabase.table("shops").insert(shop_data_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create shop"
        )
    
    shop_id = result.data[0]["id"]
    
    # Record admin shop creation on blockchain
    try:
        shop_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.SHOP_CREATE,
            user_id=current_user["id"],  # Admin user ID
            data={
                "shop_name": shop_data.name,
                "shop_id": shop_id,
                "target_user_id": target_user_id,
                "description": shop_data.description,
                "address": shop_data.address,
                "phone": shop_data.phone,
                "verified": verified,
                "action": "admin_shop_creation"
            },
            shop_id=shop_id,
            metadata={
                "source": "shops_route_admin",
                "admin_action": True,
                "auto_verified": verified
            }
        )
        
        blockchain_service.add_transaction(shop_transaction)
        
        # Update shop with blockchain transaction reference
        supabase.table("shops").update({
            "blockchain_tx_id": shop_transaction.transaction_id
        }).eq("id", shop_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Shop created successfully by admin", 
        "shop_id": shop_id,
        "verified": verified,
        "blockchain_tx_id": shop_transaction.transaction_id if 'shop_transaction' in locals() else None
    }

@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(shop_id: str):
    result = supabase.table("shops").select("*").eq("id", shop_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop = result.data[0]
    
    # Get shop's blockchain transactions for enhanced response
    try:
        shop_transactions = blockchain_service.get_transactions_by_shop(shop_id)
        shop["blockchain_activity"] = {
            "total_transactions": len(shop_transactions),
            "recent_activity": [
                {
                    "transaction_type": tx.transaction_type,
                    "timestamp": tx.timestamp,
                    "user_id": tx.user_id,
                    "data": tx.data
                }
                for tx in shop_transactions[:5]  # Last 5 transactions
            ]
        }
    except Exception as e:
        print(f"Failed to get shop blockchain transactions: {e}")
    
    return shop

@router.get("/")
async def get_shops(verified: bool = None, limit: int = 20, offset: int = 0):
    query = supabase.table("shops").select("*, users(name, email)", count="exact")
    
    if verified is not None:
        query = query.eq("verified", verified)
    
    result = query.range(offset, offset + limit - 1).execute()
    
    # Enhance with blockchain data
    shops_with_blockchain = []
    for shop in result.data:
        try:
            # Get transaction count for each shop
            shop_transactions = blockchain_service.get_transactions_by_shop(shop["id"])
            shop["blockchain_transaction_count"] = len(shop_transactions)
        except Exception as e:
            print(f"Failed to get blockchain data for shop {shop['id']}: {e}")
            shop["blockchain_transaction_count"] = 0
        
        shops_with_blockchain.append(shop)
    
    return {
        "data": shops_with_blockchain,
        "pagination": {
            "total": result.count,
            "offset": offset,
            "limit": limit
        }
    }

@router.put("/{shop_id}")
async def update_shop(shop_id: str, shop_data: ShopCreate, current_user: dict = Depends(get_current_merchant)):
    # Verify the shop belongs to the current user
    shop_result = supabase.table("shops").select("*").eq("id", shop_id).eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found or access denied")
    
    old_shop_data = shop_result.data[0]
    
    # Update shop in database
    result = supabase.table("shops").update(shop_data.dict()).eq("id", shop_id).execute()
    
    # Record shop update on blockchain
    try:
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.SHOP_UPDATE,
            user_id=current_user["id"],
            data={
                "shop_id": shop_id,
                "shop_name": shop_data.name,
                "updated_fields": list(shop_data.dict().keys()),
                "previous_data": {
                    "name": old_shop_data.get("name"),
                    "description": old_shop_data.get("description"),
                    "address": old_shop_data.get("address"),
                    "phone": old_shop_data.get("phone")
                },
                "new_data": shop_data.dict(),
                "action": "shop_update"
            },
            shop_id=shop_id,
            metadata={
                "source": "shops_route",
                "merchant_owner": True
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Shop updated successfully",
        "blockchain_tx_id": update_transaction.transaction_id if 'update_transaction' in locals() else None
    }

@router.put("/admin/{shop_id}")
async def update_shop_admin(
    shop_id: str, 
    shop_data: ShopCreate, 
    verified: bool = None,
    current_user: dict = Depends(get_current_admin)
):
    """
    Admin endpoint to update any shop
    """
    # Check if shop exists
    shop_result = supabase.table("shops").select("*").eq("id", shop_id).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    old_shop_data = shop_result.data[0]
    
    update_data = shop_data.dict()
    if verified is not None:
        update_data["verified"] = verified
    
    # Update shop in database
    result = supabase.table("shops").update(update_data).eq("id", shop_id).execute()
    
    # Record admin shop update on blockchain
    try:
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.SHOP_UPDATE,
            user_id=current_user["id"],
            data={
                "shop_id": shop_id,
                "shop_name": shop_data.name,
                "updated_fields": list(update_data.keys()),
                "previous_data": {
                    "name": old_shop_data.get("name"),
                    "description": old_shop_data.get("description"),
                    "address": old_shop_data.get("address"),
                    "phone": old_shop_data.get("phone"),
                    "verified": old_shop_data.get("verified")
                },
                "new_data": update_data,
                "verified_status_changed": verified is not None and verified != old_shop_data.get("verified"),
                "action": "admin_shop_update"
            },
            shop_id=shop_id,
            metadata={
                "source": "shops_route_admin",
                "admin_action": True
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Shop updated successfully by admin",
        "verified": verified if verified is not None else old_shop_data.get("verified"),
        "blockchain_tx_id": update_transaction.transaction_id if 'update_transaction' in locals() else None
    }

@router.post("/admin/{shop_id}/verify")
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
                "source": "shops_route_admin",
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

@router.get("/{shop_id}/blockchain-activity")
async def get_shop_blockchain_activity(
    shop_id: str,
    limit: int = 50,
    transaction_type: str = None
):
    """Get detailed blockchain activity for a specific shop"""
    try:
        # Check if shop exists
        shop_result = supabase.table("shops").select("id, name").eq("id", shop_id).execute()
        if not shop_result.data:
            raise HTTPException(status_code=404, detail="Shop not found")
        
        # Get shop transactions
        all_transactions = blockchain_service.get_transactions_by_shop(shop_id)
        
        # Filter by type if specified
        if transaction_type:
            all_transactions = [tx for tx in all_transactions if tx.transaction_type.value == transaction_type]
        
        # Apply limit
        transactions = all_transactions[:limit]
        
        # Format response
        activity = []
        for tx in transactions:
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
                "block_index": block_index,
                "product_id": tx.product_id,
                "order_id": tx.order_id
            })
        
        return {
            "shop_id": shop_id,
            "shop_name": shop_result.data[0]["name"],
            "total_transactions": len(all_transactions),
            "transactions_shown": len(activity),
            "activity": sorted(activity, key=lambda x: x["timestamp"], reverse=True)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve blockchain activity: {str(e)}"
        )