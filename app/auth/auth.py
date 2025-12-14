from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.database import supabase
from app.model.models import UserCreate
from app.utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
)
from app.dependencies import get_current_user

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

# Router
router = APIRouter(prefix="/auth", tags=["authentication"])


# =========================
# SIGNUP
# =========================
@router.post("/signup", response_model=None)
async def signup(user_data: UserCreate):
    email = user_data.email.lower().strip()

    # Check if user exists
    existing_user = (
        supabase.table("users")
        .select("id")
        .eq("email", email)
        .execute()
    )

    if existing_user.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    hashed_password = get_password_hash(user_data.password)

    new_user = {
        "name": user_data.name,
        "email": email,
        "password_hash": hashed_password,
        "type": user_data.type,
        "phone_number": user_data.phone_number,
    }

    if getattr(user_data, "profile_picture", None):
        new_user["profile_picture"] = str(user_data.profile_picture)

    result = supabase.table("users").insert(new_user).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    user_id = result.data[0]["id"]

    # Blockchain: user registration
    user_transaction = None
    try:
        user_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_REGISTER,
            user_id=user_id,
            data={
                "name": user_data.name,
                "email": email,
                "user_type": user_data.type,
                "has_phone": bool(user_data.phone_number),
                "action": "user_registration",
            },
            metadata={
                "source": "auth_signup",
                "user_agent": "web_app",
            },
        )

        blockchain_service.add_transaction(user_transaction)

        supabase.table("users").update(
            {"blockchain_tx_id": user_transaction.transaction_id}
        ).eq("id", user_id).execute()

    except Exception as e:
        print(f"[BLOCKCHAIN] Signup transaction failed: {e}")

    # Auto-create shop for merchants
    if user_data.type == "merchant":
        try:
            shop_data = {
                "user_id": user_id,
                "name": f"{user_data.name}'s Shop",
                "verified": False,
            }

            shop_result = supabase.table("shops").insert(shop_data).execute()

            if shop_result.data:
                shop_id = shop_result.data[0]["id"]

                shop_tx = blockchain_service.create_transaction(
                    transaction_type=TransactionType.SHOP_CREATE,
                    user_id=user_id,
                    shop_id=shop_id,
                    data={
                        "shop_name": shop_data["name"],
                        "verified": False,
                        "action": "shop_creation",
                    },
                    metadata={
                        "source": "auth_signup",
                        "auto_created": True,
                    },
                )

                blockchain_service.add_transaction(shop_tx)

                supabase.table("shops").update(
                    {"blockchain_tx_id": shop_tx.transaction_id}
                ).eq("id", shop_id).execute()

        except Exception as e:
            print(f"[BLOCKCHAIN] Shop creation failed: {e}")

    # Auto-mine block if threshold reached
    try:
        if len(blockchain_service.blockchain.pending_transactions) >= 5:
            blockchain_service.mine_block()
            print("[BLOCKCHAIN] Auto-mined block")
    except Exception as e:
        print(f"[BLOCKCHAIN] Auto-mining failed: {e}")

    return {
        "message": "User created successfully",
        "user_id": user_id,
        "blockchain_tx_id": user_transaction.transaction_id if user_transaction else None,
    }


# =========================
# LOGIN
# =========================
@router.post("/login", response_model=None)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    email = form_data.username.lower().strip()

    user_result = (
        supabase.table("users")
        .select("*")
        .eq("email", email)
        .execute()
    )

    if (
        not user_result.data
        or not verify_password(
            form_data.password, user_result.data[0]["password_hash"]
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    user = user_result.data[0]

    login_transaction = None
    try:
        login_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.USER_LOGIN,
            user_id=user["id"],
            data={
                "action": "user_login",
                "login_method": "password",
                "success": True,
            },
            metadata={
                "source": "auth_login",
                "ip_address": "unknown",
            },
        )

        blockchain_service.add_transaction(login_transaction)

    except Exception as e:
        print(f"[BLOCKCHAIN] Login transaction failed: {e}")

    access_token = create_access_token(
        data={
            "sub": user["email"],
            "user_id": user["id"],
            "type": user["type"],
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_type": user["type"],
        "user_id": user["id"],
        "blockchain_tx_id": (
            login_transaction.transaction_id if login_transaction else None
        ),
    }


# =========================
# CURRENT USER
# =========================
@router.get("/me", response_model=None)
async def get_me(current_user=Depends(get_current_user)):
    return current_user


# =========================
# USER BLOCKCHAIN ACTIVITY
# =========================
@router.get("/blockchain/activity", response_model=None)
async def get_user_blockchain_activity(
    current_user=Depends(get_current_user),
):
    try:
        transactions = blockchain_service.get_transactions_by_user(
            current_user["id"]
        )

        activity = [
            {
                "transaction_id": tx.transaction_id,
                "type": tx.transaction_type,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "confirmed": any(
                    tx in block.transactions
                    for block in blockchain_service.blockchain.chain
                ),
            }
            for tx in transactions
        ]

        return {
            "user_id": current_user["id"],
            "total_transactions": len(activity),
            "activity": sorted(
                activity, key=lambda x: x["timestamp"], reverse=True
            ),
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blockchain activity",
        )


# =========================
# MANUAL BLOCK MINING (ADMIN ONLY)
# =========================
@router.post("/blockchain/manual-mine", response_model=None)
async def manual_mine_block(
    current_user=Depends(get_current_user),
):
    if current_user["type"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to mine blocks",
        )

    if not blockchain_service.blockchain.pending_transactions:
        return {"message": "No pending transactions to mine"}

    try:
        new_block = blockchain_service.mine_block()

        return {
            "message": "Block mined successfully",
            "block": {
                "index": new_block.index,
                "timestamp": new_block.timestamp,
                "transactions_count": len(new_block.transactions),
                "hash": new_block.hash,
            },
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mine block",
        )
