from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.database import supabase
from app.dependencies import get_current_user
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
import json

router = APIRouter(prefix="/cart", tags=["cart"])

class CartItemCreate(BaseModel):
    product_id: str
    quantity: int = 1

class CartItemUpdate(BaseModel):
    quantity: int

@router.get("/", response_model=Dict[str, Any])
async def get_cart(current_user: dict = Depends(get_current_user)):
    """Get user's shopping cart"""
    cart_result = supabase.table("cart_items").select(
        "*, products(title, price, images, stock, shops(name))"
    ).eq("user_id", current_user["id"]).execute()
    
    cart_items = []
    total_price = 0
    total_items = 0
    
    for item in cart_result.data:
        product = item["products"]
        item_total = product["price"] * item["quantity"]
        total_price += item_total
        total_items += item["quantity"]
        
        cart_items.append({
            "id": item["id"],
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "title": product["title"],
            "price": product["price"],
            "images": product["images"],
            "stock": product["stock"],
            "shop_name": product["shops"]["name"],
            "item_total": item_total,
            "added_at": item["created_at"]
        })
    
    return {
        "items": cart_items,
        "summary": {
            "total_items": total_items,
            "total_price": total_price,
            "estimated_tax": total_price * 0.1,  # 10% tax estimate
            "shipping_estimate": 0,
            "grand_total": total_price * 1.1
        }
    }

@router.post("/items", status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    item: CartItemCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add item to cart"""
    # Check if product exists and is in stock
    product_result = supabase.table("products").select(
        "id, title, price, stock, shop_id"
    ).eq("id", item.product_id).execute()
    
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = product_result.data[0]
    
    if product["stock"] < item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough stock. Only {product['stock']} available"
        )
    
    # Check if item already in cart
    existing = supabase.table("cart_items").select("*").eq(
        "user_id", current_user["id"]
    ).eq("product_id", item.product_id).execute()
    
    if existing.data:
        # Update quantity
        new_quantity = existing.data[0]["quantity"] + item.quantity
        
        if new_quantity > product["stock"]:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock. Maximum {product['stock']} available"
            )
        
        result = supabase.table("cart_items").update({
            "quantity": new_quantity
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        # Add new item
        result = supabase.table("cart_items").insert({
            "user_id": current_user["id"],
            "product_id": item.product_id,
            "quantity": item.quantity
        }).execute()
    
    # Record on blockchain
    try:
        cart_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_CREATE,  # Use appropriate type
            user_id=current_user["id"],
            data={
                "action": "add_to_cart",
                "product_id": item.product_id,
                "product_title": product["title"],
                "quantity": item.quantity,
                "price": product["price"],
                "total": product["price"] * item.quantity
            },
            product_id=item.product_id,
            metadata={
                "source": "cart_route",
                "shop_id": product["shop_id"],
                "new_item": not existing.data
            }
        )
        
        blockchain_service.add_transaction(cart_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {"message": "Item added to cart"}

@router.put("/items/{item_id}")
async def update_cart_item(
    item_id: str,
    update: CartItemUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update cart item quantity"""
    # Get cart item
    cart_item_result = supabase.table("cart_items").select(
        "*, products(stock, title, price)"
    ).eq("id", item_id).eq("user_id", current_user["id"]).execute()
    
    if not cart_item_result.data:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    cart_item = cart_item_result.data[0]
    product = cart_item["products"]
    
    if update.quantity <= 0:
        # Remove item if quantity is 0 or negative
        supabase.table("cart_items").delete().eq("id", item_id).execute()
        return {"message": "Item removed from cart"}
    
    if update.quantity > product["stock"]:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough stock. Maximum {product['stock']} available"
        )
    
    old_quantity = cart_item["quantity"]
    result = supabase.table("cart_items").update({
        "quantity": update.quantity
    }).eq("id", item_id).execute()
    
    # Record on blockchain
    try:
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_UPDATE,
            user_id=current_user["id"],
            data={
                "action": "update_cart_item",
                "cart_item_id": item_id,
                "product_id": cart_item["product_id"],
                "product_title": product["title"],
                "old_quantity": old_quantity,
                "new_quantity": update.quantity,
                "price": product["price"]
            },
            product_id=cart_item["product_id"],
            metadata={
                "source": "cart_route",
                "quantity_change": update.quantity - old_quantity
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {"message": "Cart item updated"}

@router.delete("/items/{item_id}")
async def remove_cart_item(
    item_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove item from cart"""
    # Get cart item before deletion for blockchain record
    cart_item_result = supabase.table("cart_items").select(
        "*, products(title, price)"
    ).eq("id", item_id).eq("user_id", current_user["id"]).execute()
    
    if not cart_item_result.data:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    cart_item = cart_item_result.data[0]
    
    # Delete item
    result = supabase.table("cart_items").delete().eq("id", item_id).execute()
    
    # Record on blockchain
    try:
        remove_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_UPDATE,
            user_id=current_user["id"],
            data={
                "action": "remove_cart_item",
                "cart_item_id": item_id,
                "product_id": cart_item["product_id"],
                "product_title": cart_item["products"]["title"],
                "quantity": cart_item["quantity"],
                "price": cart_item["products"]["price"]
            },
            product_id=cart_item["product_id"],
            metadata={
                "source": "cart_route",
                "permanent_removal": True
            }
        )
        
        blockchain_service.add_transaction(remove_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {"message": "Item removed from cart"}

@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(current_user: dict = Depends(get_current_user)):
    """Clear entire cart"""
    # Get cart items before deletion for blockchain record
    cart_items_result = supabase.table("cart_items").select(
        "*, products(title)"
    ).eq("user_id", current_user["id"]).execute()
    
    # Delete all items
    supabase.table("cart_items").delete().eq("user_id", current_user["id"]).execute()
    
    # Record on blockchain
    try:
        if cart_items_result.data:
            clear_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.ORDER_UPDATE,
                user_id=current_user["id"],
                data={
                    "action": "clear_cart",
                    "items_removed": len(cart_items_result.data),
                    "item_details": [
                        {
                            "product_id": item["product_id"],
                            "product_title": item["products"]["title"],
                            "quantity": item["quantity"]
                        }
                        for item in cart_items_result.data
                    ]
                },
                metadata={
                    "source": "cart_route",
                    "complete_clear": True
                }
            )
            
            blockchain_service.add_transaction(clear_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return None

@router.get("/count")
async def get_cart_count(current_user: dict = Depends(get_current_user)):
    """Get total number of items in cart"""
    result = supabase.table("cart_items").select(
        "sum(quantity)"
    ).eq("user_id", current_user["id"]).execute()
    
    total_quantity = result.data[0]["sum"] if result.data and result.data[0]["sum"] else 0
    
    return {"total_items": total_quantity}

@router.get("/total")
async def get_cart_total(current_user: dict = Depends(get_current_user)):
    """Get cart total price"""
    cart_result = supabase.table("cart_items").select(
        "quantity, products(price)"
    ).eq("user_id", current_user["id"]).execute()
    
    total_price = 0
    for item in cart_result.data:
        total_price += item["products"]["price"] * item["quantity"]
    
    return {
        "subtotal": total_price,
        "tax": total_price * 0.1,
        "total": total_price * 1.1
    }