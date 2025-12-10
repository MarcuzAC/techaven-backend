from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import get_current_user
from typing import Optional

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
async def get_users(
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    type: str = Query(None)
):
    from app.database import supabase
    
    # Build the query - updated to include new fields
    query = supabase.table("users").select(
        "id, name, email, type, phone_number, profile_picture, created_at, blockchain_tx_id", 
        count="exact"
    )
    
    # Apply filters
    if search:
        query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%,phone_number.ilike.%{search}%")
    
    if type:
        query = query.eq("type", type)
    
    # Apply pagination
    query = query.range(skip, skip + limit - 1)
    
    # Execute query
    result = query.execute()
    
    # Transform data to match frontend expectations
    users_data = []
    for user in result.data:
        # Split name into first_name and last_name for frontend
        name_parts = user.get('name', '').split(' ', 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        users_data.append({
            "id": user.get('id'),
            "first_name": first_name,
            "last_name": last_name,
            "email": user.get('email'),
            "phone_number": user.get('phone_number'),
            "profile_picture": str(user.get('profile_picture')) if user.get('profile_picture') else None,
            "role": user.get('type', 'customer'),  # Map 'type' to 'role' for frontend
            "status": "active",  # Default status since your model doesn't have status
            "created_at": user.get('created_at'),
            "blockchain_tx_id": user.get('blockchain_tx_id')  # Include blockchain reference
        })
    
    return {
        "data": users_data,
        "pagination": {
            "total": result.count,
            "skip": skip,
            "limit": limit
        }
    }

@router.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    # Get user's blockchain activity for enhanced profile
    try:
        user_transactions = blockchain_service.get_transactions_by_user(current_user["id"])
        current_user["blockchain_activity_count"] = len(user_transactions)
        
        # Get recent transactions (last 5)
        recent_activity = []
        for tx in user_transactions[:5]:
            recent_activity.append({
                "type": tx.transaction_type,
                "timestamp": tx.timestamp,
                "data": tx.data
            })
        current_user["recent_blockchain_activity"] = recent_activity
        
    except Exception as e:
        print(f"Failed to get user blockchain activity: {e}")
    
    return current_user

@router.get("/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    from app.database import supabase
    
    # Updated to include phone_number and profile_picture
    result = supabase.table("users").select(
        "id, name, email, type, phone_number, profile_picture, created_at, blockchain_tx_id"
    ).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = result.data[0]
    
    # Get user's blockchain transactions for enhanced response
    try:
        user_transactions = blockchain_service.get_transactions_by_user(user_id)
        user["blockchain_activity"] = {
            "total_transactions": len(user_transactions),
            "recent_activity": [
                {
                    "transaction_type": tx.transaction_type,
                    "timestamp": tx.timestamp,
                    "data": tx.data
                }
                for tx in user_transactions[:10]  # Last 10 transactions
            ]
        }
    except Exception as e:
        print(f"Failed to get user blockchain transactions: {e}")
    
    # Transform the data to match frontend expectations
    name_parts = user.get('name', '').split(' ', 1)
    first_name = name_parts[0] if name_parts else ''
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    return {
        "id": user.get('id'),
        "first_name": first_name,
        "last_name": last_name,
        "email": user.get('email'),
        "phone_number": user.get('phone_number'),
        "profile_picture": str(user.get('profile_picture')) if user.get('profile_picture') else None,
        "role": user.get('type', 'customer'),
        "status": "active",
        "created_at": user.get('created_at'),
        "blockchain_tx_id": user.get('blockchain_tx_id'),
        "blockchain_activity": user.get('blockchain_activity', {})
    }

@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str, 
    status: str,
    current_user: dict = Depends(get_current_user)
):
    from app.database import supabase
    
    # Check if user exists - updated to include new fields
    user_result = supabase.table("users").select(
        "id, name, email, type, phone_number, profile_picture"
    ).eq("id", user_id).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = user_result.data[0]
    
    # Record status update on blockchain
    try:
        status_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,  # Using existing type or create USER_UPDATE type
            user_id=current_user["id"],  # The admin/user making the change
            data={
                "action": "user_status_update",
                "target_user_id": user_id,
                "target_user_name": user["name"],
                "target_user_phone": user.get("phone_number"),
                "new_status": status,
                "previous_status": "unknown"  # You might want to track previous status
            },
            metadata={
                "source": "users_route",
                "admin_action": True
            }
        )
        
        blockchain_service.add_transaction(status_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with the operation even if blockchain recording fails
    
    return {
        "message": f"User status would be updated to {status}", 
        "user_id": user_id,
        "blockchain_tx_id": status_transaction.transaction_id if 'status_transaction' in locals() else None
    }

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    from app.database import supabase
    
    # Get user details before deletion for blockchain record
    user_result = supabase.table("users").select(
        "id, name, email, type, phone_number, profile_picture"
    ).eq("id", user_id).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = user_result.data[0]
    
    # Record user deletion on blockchain
    try:
        delete_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,  # Using existing type or create USER_DELETE type
            user_id=current_user["id"],  # The admin/user making the deletion
            data={
                "action": "user_deletion",
                "deleted_user_id": user_id,
                "deleted_user_name": user["name"],
                "deleted_user_email": user["email"],
                "deleted_user_phone": user.get("phone_number"),
                "deleted_user_type": user["type"]
            },
            metadata={
                "source": "users_route",
                "admin_action": True,
                "permanent_deletion": True
            }
        )
        
        blockchain_service.add_transaction(delete_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with deletion even if blockchain recording fails
    
    # Perform the actual deletion
    result = supabase.table("users").delete().eq("id", user_id).execute()
    
    # Also delete associated shops if merchant
    if user["type"] == "merchant":
        supabase.table("shops").delete().eq("user_id", user_id).execute()
    
    return {
        "message": "User deleted successfully",
        "deleted_user": {
            "id": user_id,
            "name": user["name"],
            "email": user["email"],
            "phone_number": user.get("phone_number")
        },
        "blockchain_tx_id": delete_transaction.transaction_id if 'delete_transaction' in locals() else None
    }

@router.get("/{user_id}/blockchain-activity")
async def get_user_blockchain_activity(
    user_id: str, 
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=1000),
    transaction_type: Optional[str] = Query(None)
):
    """Get detailed blockchain activity for a specific user"""
    try:
        # Check if user exists
        from app.database import supabase
        user_result = supabase.table("users").select("id, name, phone_number").eq("id", user_id).execute()
        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user transactions
        all_transactions = blockchain_service.get_transactions_by_user(user_id)
        
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
                "timestamp": tx.timestamp,
                "data": tx.data,
                "metadata": tx.metadata,
                "confirmed": confirmed,
                "block_index": block_index,
                "shop_id": tx.shop_id,
                "product_id": tx.product_id,
                "order_id": tx.order_id
            })
        
        return {
            "user_id": user_id,
            "user_name": user_result.data[0]["name"],
            "user_phone": user_result.data[0].get("phone_number"),
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

@router.post("/{user_id}/profile-update")
async def update_user_profile(
    user_id: str,
    profile_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update user profile and record on blockchain"""
    from app.database import supabase
    
    # Check if user exists and current user has permission
    user_result = supabase.table("users").select(
        "id, name, email, phone_number, profile_picture"
    ).eq("id", user_id).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Ensure users can only update their own profile unless admin
    if current_user["id"] != user_id and current_user.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")
    
    # Validate and prepare update data
    update_data = {}
    
    if "name" in profile_data:
        update_data["name"] = profile_data["name"]
    
    if "email" in profile_data:
        update_data["email"] = profile_data["email"]
    
    if "phone_number" in profile_data:
        update_data["phone_number"] = profile_data["phone_number"]
    
    if "profile_picture" in profile_data:
        update_data["profile_picture"] = profile_data["profile_picture"]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    # Update user profile in database
    result = supabase.table("users").update(update_data).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update profile")
    
    # Record profile update on blockchain
    try:
        profile_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,  # Using existing type
            user_id=current_user["id"],
            data={
                "action": "profile_update",
                "updated_fields": list(update_data.keys()),
                "previous_data": user_result.data[0],
                "new_data": update_data
            },
            metadata={
                "source": "users_route",
                "self_update": current_user["id"] == user_id,
                "has_profile_picture": "profile_picture" in update_data,
                "has_phone_update": "phone_number" in update_data
            }
        )
        
        blockchain_service.add_transaction(profile_transaction)
        
        # Update user with new blockchain transaction reference
        supabase.table("users").update({
            "blockchain_tx_id": profile_transaction.transaction_id
        }).eq("id", user_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Profile updated successfully",
        "updated_fields": list(update_data.keys()),
        "blockchain_tx_id": profile_transaction.transaction_id if 'profile_transaction' in locals() else None,
        "user": result.data[0]
    }