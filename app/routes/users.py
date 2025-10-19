from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import get_current_user
from typing import Optional

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
    
    # Build the query - using your actual model fields
    query = supabase.table("users").select("id, name, email, type, created_at", count="exact")
    
    # Apply filters
    if search:
        query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%")
    
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
            "role": user.get('type', 'customer'),  # Map 'type' to 'role' for frontend
            "status": "active",  # Default status since your model doesn't have status
            "created_at": user.get('created_at')
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
    return current_user

@router.get("/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    from app.database import supabase
    result = supabase.table("users").select("id, name, email, type, created_at").eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = result.data[0]
    # Transform the data to match frontend expectations
    name_parts = user.get('name', '').split(' ', 1)
    first_name = name_parts[0] if name_parts else ''
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    return {
        "id": user.get('id'),
        "first_name": first_name,
        "last_name": last_name,
        "email": user.get('email'),
        "role": user.get('type', 'customer'),
        "status": "active",
        "created_at": user.get('created_at')
    }

@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str, 
    status: str,
    current_user: dict = Depends(get_current_user)
):
    # Since your User model doesn't have status, we'll handle this differently
    # For now, we'll just return a success message since we can't update the status in the database
    # In a real implementation, you would need to add a status field to your users table
    from app.database import supabase
    
    # Check if user exists
    user_result = supabase.table("users").select("id").eq("id", user_id).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # If you add status to your database later, uncomment this:
    # result = supabase.table("users").update({"status": status}).eq("id", user_id).execute()
    # return result.data[0]
    
    return {"message": f"User status would be updated to {status}", "user_id": user_id}

@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    from app.database import supabase
    result = supabase.table("users").delete().eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}