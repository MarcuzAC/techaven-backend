from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List
import os
from datetime import datetime
import uuid
from app.dependencies import get_current_user
from app.database import supabase

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/users", tags=["users"])

# ==================== ORIGINAL ENDPOINTS ====================

@router.get("/")
async def get_users(
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    type: str = Query(None)
):
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
            transaction_type=TransactionType.USER_UPDATE,
            user_id=current_user["id"],  # The admin/user making the change
            data={
                "action": "user_status_update",
                "target_user_id": user_id,
                "target_user_name": user["name"],
                "target_user_phone": user.get("phone_number"),
                "new_status": status,
                "previous_status": "unknown"
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
    # Get user details before deletion for blockchain record
    user_result = supabase.table("users").select(
        "id, name, email, type, phone_number, profile_picture"
    ).eq("id", user_id).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = user_result.data[0]
    
    # First, delete profile picture from storage if it exists
    if user.get("profile_picture"):
        try:
            bucket_name = "profile_pictures"
            filename = user["profile_picture"].split('/')[-1].split('?')[0]
            supabase.storage.from_(bucket_name).remove([filename])
        except Exception as e:
            print(f"Failed to delete profile picture from storage: {e}")
    
    # Record user deletion on blockchain
    try:
        delete_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_DELETE,
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

# ==================== NEW PROFILE ENDPOINTS ====================

@router.post("/profile/update")
async def update_user_profile(
    name: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """Update user profile information"""
    # Get current user data for comparison
    user_result = supabase.table("users").select(
        "id, name, email, phone_number, profile_picture"
    ).eq("id", current_user["id"]).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    current_data = user_result.data[0]
    
    # Prepare update data
    update_data = {}
    
    if name and name != current_data.get("name"):
        update_data["name"] = name
    
    if phone_number and phone_number != current_data.get("phone_number"):
        # Validate phone number format
        import re
        phone_pattern = r'^\+?[1-9]\d{1,14}$'
        if not re.match(phone_pattern, phone_number):
            raise HTTPException(
                status_code=400, 
                detail="Invalid phone number format. Use international format (e.g., +265XXXXXXXXX)"
            )
        update_data["phone_number"] = phone_number
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No changes provided")
    
    # Add updated_at timestamp if the column exists
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    # Update user profile in database
    result = supabase.table("users").update(update_data).eq("id", current_user["id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update profile")
    
    # Record profile update on blockchain
    try:
        profile_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_UPDATE,
            user_id=current_user["id"],
            data={
                "action": "profile_update",
                "updated_fields": list(update_data.keys()),
                "previous_data": current_data,
                "new_data": update_data
            },
            metadata={
                "source": "users_profile_update",
                "update_type": "text_fields",
                "has_phone_update": "phone_number" in update_data
            }
        )
        
        blockchain_service.add_transaction(profile_transaction)
        
        # Update blockchain reference if column exists
        try:
            supabase.table("users").update({
                "blockchain_tx_id": profile_transaction.transaction_id
            }).eq("id", current_user["id"]).execute()
        except:
            pass  # Skip if blockchain_tx_id column doesn't exist
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue even if blockchain recording fails
    
    return {
        "message": "Profile updated successfully",
        "updated_fields": list(update_data.keys()),
        "blockchain_tx_id": profile_transaction.transaction_id if 'profile_transaction' in locals() else None,
        "user": result.data[0]
    }

@router.post("/profile/upload-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload and update user profile picture using Supabase Storage"""
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/jpg']
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed types: {', '.join([t.split('/')[1] for t in allowed_types])}"
        )
    
    # Validate file size (max 5MB)
    max_size = 5 * 1024 * 1024  # 5MB
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 5MB"
        )
    
    # Get current profile picture for comparison
    user_result = supabase.table("users").select(
        "id, name, profile_picture"
    ).eq("id", current_user["id"]).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    current_profile_pic = user_result.data[0].get("profile_picture")
    
    try:
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        if not file_extension:
            # Determine extension from content type
            ext_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/jpg': '.jpg'
            }
            file_extension = ext_map.get(file.content_type, '.jpg')
        
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Read file content
        file_content = await file.read()
        
        # Upload to Supabase Storage
        bucket_name = "profile_pictures"
        
        # Create bucket if it doesn't exist (you should create this bucket in Supabase dashboard)
        try:
            # Try to upload directly
            upload_result = supabase.storage.from_(bucket_name).upload(
                unique_filename,
                file_content,
                {
                    "content-type": file.content_type,
                    "cache-control": "3600",
                    "upsert": "true"
                }
            )
        except Exception as e:
            print(f"Upload error: {e}")
            # Bucket might not exist, you should create it in Supabase dashboard
            raise HTTPException(
                status_code=500,
                detail=f"Storage bucket error. Please ensure '{bucket_name}' bucket exists in Supabase Storage."
            )
        
        # Get public URL for the uploaded file
        public_url_result = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
        
        # Update user profile with new image URL
        update_data = {
            "profile_picture": public_url_result,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("users").update(update_data).eq("id", current_user["id"]).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to update profile picture")
        
        # Delete old profile picture from storage if it exists
        if current_profile_pic:
            try:
                # Extract filename from URL
                old_filename = current_profile_pic.split('/')[-1].split('?')[0]
                supabase.storage.from_(bucket_name).remove([old_filename])
            except Exception as e:
                print(f"Failed to delete old profile picture: {e}")
                # Continue anyway
        
        # Record profile picture update on blockchain
        try:
            pic_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "profile_picture_update",
                    "previous_picture": current_profile_pic,
                    "new_picture": public_url_result,
                    "file_size": file_size,
                    "file_type": file.content_type,
                    "storage_bucket": bucket_name,
                    "storage_filename": unique_filename
                },
                metadata={
                    "source": "users_profile_upload",
                    "update_type": "profile_picture",
                    "filename": unique_filename,
                    "content_type": file.content_type,
                    "storage_provider": "supabase"
                }
            )
            
            blockchain_service.add_transaction(pic_transaction)
            
            # Update blockchain reference if column exists
            try:
                supabase.table("users").update({
                    "blockchain_tx_id": pic_transaction.transaction_id
                }).eq("id", current_user["id"]).execute()
            except:
                pass
            
        except Exception as e:
            print(f"Blockchain transaction failed: {e}")
        
        return {
            "message": "Profile picture uploaded successfully",
            "image_url": public_url_result,
            "filename": unique_filename,
            "file_size": file_size,
            "content_type": file.content_type,
            "blockchain_tx_id": pic_transaction.transaction_id if 'pic_transaction' in locals() else None,
            "user": result.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading profile picture: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to upload profile picture"
        )

@router.post("/profile/remove-picture")
async def remove_profile_picture(
    current_user: dict = Depends(get_current_user)
):
    """Remove user profile picture from Supabase Storage"""
    
    # Get current profile picture
    user_result = supabase.table("users").select(
        "id, name, profile_picture"
    ).eq("id", current_user["id"]).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    current_profile_pic = user_result.data[0].get("profile_picture")
    
    if not current_profile_pic:
        raise HTTPException(status_code=400, detail="No profile picture to remove")
    
    try:
        bucket_name = "profile_pictures"
        
        # Extract filename from URL
        filename = current_profile_pic.split('/')[-1].split('?')[0]
        
        # Delete from Supabase Storage
        try:
            supabase.storage.from_(bucket_name).remove([filename])
        except Exception as e:
            print(f"Failed to delete from storage (file might not exist): {e}")
            # Continue anyway
        
        # Update user profile to remove picture
        update_data = {
            "profile_picture": None,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("users").update(update_data).eq("id", current_user["id"]).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to remove profile picture")
        
        # Record removal on blockchain
        try:
            remove_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.USER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "profile_picture_removal",
                    "removed_picture": current_profile_pic,
                    "storage_bucket": bucket_name,
                    "storage_filename": filename
                },
                metadata={
                    "source": "users_profile_remove",
                    "update_type": "remove_picture",
                    "storage_provider": "supabase"
                }
            )
            
            blockchain_service.add_transaction(remove_transaction)
            
            # Update blockchain reference if column exists
            try:
                supabase.table("users").update({
                    "blockchain_tx_id": remove_transaction.transaction_id
                }).eq("id", current_user["id"]).execute()
            except:
                pass
            
        except Exception as e:
            print(f"Blockchain transaction failed: {e}")
        
        return {
            "message": "Profile picture removed successfully",
            "blockchain_tx_id": remove_transaction.transaction_id if 'remove_transaction' in locals() else None,
            "user": result.data[0]
        }
        
    except Exception as e:
        print(f"Error removing profile picture: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to remove profile picture"
        )

@router.post("/change-password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Change user password"""
    from app.utils.security import verify_password, get_password_hash
    
    # Validate new password
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")
    
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    # Get user with password hash
    user_result = supabase.table("users").select(
        "id, name, email, password_hash"
    ).eq("id", current_user["id"]).execute()
    
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = user_result.data[0]
    
    # Verify current password
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Hash new password
    new_password_hash = get_password_hash(new_password)
    
    # Update password in database
    update_data = {
        "password_hash": new_password_hash,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    result = supabase.table("users").update(update_data).eq("id", current_user["id"]).execute()
    
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update password")
    
    # Record password change on blockchain
    try:
        password_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_UPDATE,
            user_id=current_user["id"],
            data={
                "action": "password_change",
                "password_changed": True
            },
            metadata={
                "source": "users_change_password",
                "update_type": "security"
            }
        )
        
        blockchain_service.add_transaction(password_transaction)
        
        # Update blockchain reference if column exists
        try:
            supabase.table("users").update({
                "blockchain_tx_id": password_transaction.transaction_id
            }).eq("id", current_user["id"]).execute()
        except:
            pass
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Password changed successfully",
        "blockchain_tx_id": password_transaction.transaction_id if 'password_transaction' in locals() else None
    }