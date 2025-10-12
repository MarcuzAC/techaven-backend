from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.database import supabase
from app.models import UserCreate, UserResponse, UserLogin
from app.utils.security import get_password_hash, verify_password, create_access_token
from app.dependencies import get_current_user

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
    
    if user_data.type == "merchant":
        # Create a shop entry for merchants
        shop_data = {
            "user_id": result.data[0]["id"],
            "name": f"{user_data.name}'s Shop",
            "verified": False
        }
        supabase.table("shops").insert(shop_data).execute()
    
    return {"message": "User created successfully", "user_id": result.data[0]["id"]}

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_result = supabase.table("users").select("*").eq("email", form_data.username).execute()
    
    if not user_result.data or not verify_password(form_data.password, user_result.data[0]["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    user = user_result.data[0]
    access_token = create_access_token(
        data={"sub": user["email"], "type": user["type"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_type": user["type"],
        "user_id": user["id"]
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user