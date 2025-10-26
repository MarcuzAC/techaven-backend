from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.database import supabase
from app.model.models import UserCreate, UserResponse, UserLogin
from app.utils.security import get_password_hash, verify_password, create_access_token
from app.dependencies import get_current_user

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/signup", response_model=dict)
async def signup(user_data: UserCreate):
    # Check if user exists
    existing_user = supabase.table("users").select("*").eq("email", user_data.email).execute()
    if existing_user.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    hashed_password = get_password_hash(user_data.password)
    new_user = {
        "name": user_data.name,
        "email": user_data.email,
        "password_hash": hashed_password,
        "type": user_data.type
    }
    
    result = supabase.table("users").insert(new_user).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )
    
    user_id = result.data[0]["id"]
    
    # Create blockchain transaction for user registration
    try:
        user_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,
            user_id=user_id,
            data={
                "name": user_data.name,
                "email": user_data.email,
                "user_type": user_data.type,
                "action": "user_registration"
            },
            metadata={
                "source": "auth_signup",
                "user_agent": "web_app"  # You can get this from request headers if needed
            }
        )
        
        # Add to pending transactions
        blockchain_tx_id = blockchain_service.add_transaction(user_transaction)
        
        # Update user with blockchain transaction reference
        supabase.table("users").update({
            "blockchain_tx_id": user_transaction.transaction_id
        }).eq("id", user_id).execute()
        
    except Exception as e:
        # Log the error but don't fail the user registration
        print(f"Blockchain transaction failed: {e}")
        # Continue with user creation even if blockchain fails
    
    # Create shop for merchants and record on blockchain
    if user_data.type == "merchant":
        try:
            shop_data = {
                "user_id": user_id,
                "name": f"{user_data.name}'s Shop",
                "verified": False
            }
            shop_result = supabase.table("shops").insert(shop_data).execute()
            
            if shop_result.data:
                shop_id = shop_result.data[0]["id"]
                
                # Create blockchain transaction for shop creation
                shop_transaction = blockchain_service.create_transaction(
                    transaction_type=TransactionType.SHOP_CREATE,
                    user_id=user_id,
                    data={
                        "shop_name": shop_data["name"],
                        "verified": False,
                        "action": "shop_creation"
                    },
                    shop_id=shop_id,
                    metadata={
                        "source": "auth_signup",
                        "auto_created": True
                    }
                )
                
                # Add to pending transactions
                blockchain_service.add_transaction(shop_transaction)
                
                # Update shop with blockchain transaction reference
                supabase.table("shops").update({
                    "blockchain_tx_id": shop_transaction.transaction_id
                }).eq("id", shop_id).execute()
                
        except Exception as e:
            # Log the error but don't fail the user registration
            print(f"Shop creation blockchain transaction failed: {e}")
    
    # Auto-mine a block if there are enough pending transactions (optional)
    try:
        if len(blockchain_service.blockchain.pending_transactions) >= 5:  # Adjust threshold as needed
            blockchain_service.mine_block()
            print("Auto-mined block due to pending transactions threshold")
    except Exception as e:
        print(f"Auto-mining failed: {e}")
    
    return {
        "message": "User created successfully", 
        "user_id": user_id,
        "blockchain_tx_id": user_transaction.transaction_id if 'user_transaction' in locals() else None
    }

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_result = supabase.table("users").select("*").eq("email", form_data.username).execute()
    
    if not user_result.data or not verify_password(form_data.password, user_result.data[0]["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    user = user_result.data[0]
    
    # Create blockchain transaction for login (optional - for audit trail)
    try:
        login_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,  # Reusing type or create new LOGIN type
            user_id=user["id"],
            data={
                "action": "user_login",
                "login_method": "password",
                "success": True
            },
            metadata={
                "source": "auth_login",
                "ip_address": "unknown"  # You can get this from request if needed
            }
        )
        
        blockchain_service.add_transaction(login_transaction)
        
    except Exception as e:
        # Don't fail login if blockchain recording fails
        print(f"Login blockchain transaction failed: {e}")
    
    access_token = create_access_token(
        data={"sub": user["email"], "type": user["type"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_type": user["type"],
        "user_id": user["id"],
        "blockchain_tx_id": login_transaction.transaction_id if 'login_transaction' in locals() else None
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    # Get user's blockchain transactions for enhanced response
    try:
        user_transactions = blockchain_service.get_transactions_by_user(current_user["id"])
        # You could include transaction count in response if needed
        # current_user["blockchain_activity_count"] = len(user_transactions)
    except Exception as e:
        print(f"Failed to get user blockchain transactions: {e}")
    
    return current_user

# Additional blockchain-related auth endpoints
@router.get("/blockchain/activity")
async def get_user_blockchain_activity(current_user: dict = Depends(get_current_user)):
    """Get all blockchain transactions for the current user"""
    try:
        transactions = blockchain_service.get_transactions_by_user(current_user["id"])
        
        # Convert to response format
        activity = []
        for tx in transactions:
            activity.append({
                "transaction_id": tx.transaction_id,
                "type": tx.transaction_type,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "confirmed": any(block for block in blockchain_service.blockchain.chain if tx in block.transactions)
            })
        
        return {
            "user_id": current_user["id"],
            "total_transactions": len(activity),
            "activity": sorted(activity, key=lambda x: x["timestamp"], reverse=True)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve blockchain activity: {str(e)}"
        )

@router.post("/blockchain/manual-mine")
async def manual_mine_block(current_user: dict = Depends(get_current_user)):
    """Manually mine a block (admin or privileged users only)"""
    # Optional: Add permission check here
    if current_user["type"] not in ["admin", "merchant"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to mine blocks"
        )
    
    try:
        if not blockchain_service.blockchain.pending_transactions:
            return {"message": "No pending transactions to mine"}
        
        new_block = blockchain_service.mine_block()
        
        return {
            "message": "Block mined successfully",
            "block": {
                "index": new_block.index,
                "timestamp": new_block.timestamp,
                "transactions_count": len(new_block.transactions),
                "hash": new_block.hash
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mine block: {str(e)}"
        )