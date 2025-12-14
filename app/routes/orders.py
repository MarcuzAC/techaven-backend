from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from app.database import supabase
from app.dependencies import get_current_user, get_current_merchant
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
from app.model.models import OrderStatus
import json
import uuid

router = APIRouter(prefix="/orders", tags=["orders"])

class ShippingAddress(BaseModel):
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "Malawi"
    is_default: bool = False

class OrderCreate(BaseModel):
    shipping_address: ShippingAddress
    shipping_method_id: str
    payment_method_id: str
    coupon_code: Optional[str] = None
    notes: Optional[str] = None

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    """Create order from cart"""
    # Get user's cart items
    cart_result = supabase.table("cart_items").select(
        "*, products(id, title, price, stock, shop_id, shops(name))"
    ).eq("user_id", current_user["id"]).execute()
    
    if not cart_result.data:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    # Validate stock and calculate totals
    order_items = []
    shop_totals = {}
    grand_total = 0
    
    for cart_item in cart_result.data:
        product = cart_item["products"]
        
        # Check stock
        if product["stock"] < cart_item["quantity"]:
            raise HTTPException(
                status_code=400,
                detail=f"Product '{product['title']}' only has {product['stock']} in stock"
            )
        
        item_total = product["price"] * cart_item["quantity"]
        grand_total += item_total
        
        # Track shop totals
        shop_id = product["shop_id"]
        if shop_id not in shop_totals:
            shop_totals[shop_id] = {
                "shop_name": product["shops"]["name"],
                "total": 0,
                "items": []
            }
        
        shop_totals[shop_id]["total"] += item_total
        shop_totals[shop_id]["items"].append({
            "product_id": product["id"],
            "title": product["title"],
            "quantity": cart_item["quantity"],
            "price": product["price"],
            "total": item_total
        })
        
        order_items.append({
            "product_id": product["id"],
            "product_title": product["title"],
            "quantity": cart_item["quantity"],
            "price": product["price"],
            "total": item_total,
            "shop_id": shop_id,
            "shop_name": product["shops"]["name"]
        })
    
    # Get shipping cost
    shipping_result = supabase.table("shipping_methods").select(
        "id, name, cost, estimated_days"
    ).eq("id", order_data.shipping_method_id).execute()
    
    if not shipping_result.data:
        raise HTTPException(status_code=404, detail="Shipping method not found")
    
    shipping_method = shipping_result.data[0]
    shipping_cost = shipping_method["cost"]
    grand_total += shipping_cost
    
    # Apply coupon if provided
    discount = 0
    if order_data.coupon_code:
        coupon_result = supabase.table("coupons").select("*").eq(
            "code", order_data.coupon_code
        ).eq("is_active", True).execute()
        
        if coupon_result.data:
            coupon = coupon_result.data[0]
            # Validate coupon (check expiry, usage limits, etc.)
            if coupon["expires_at"] and datetime.fromisoformat(coupon["expires_at"]) < datetime.now():
                raise HTTPException(status_code=400, detail="Coupon has expired")
            
            if coupon["max_uses"] and coupon["times_used"] >= coupon["max_uses"]:
                raise HTTPException(status_code=400, detail="Coupon usage limit reached")
            
            # Calculate discount
            if coupon["discount_type"] == "percentage":
                discount = grand_total * (coupon["discount_value"] / 100)
            else:  # fixed amount
                discount = coupon["discount_value"]
            
            grand_total -= discount
    
    # Create order
    order_id = str(uuid.uuid4())
    
    order_result = supabase.table("orders").insert({
        "id": order_id,
        "user_id": current_user["id"],
        "total_amount": grand_total,
        "shipping_cost": shipping_cost,
        "discount": discount,
        "status": OrderStatus.PENDING,
        "shipping_address": order_data.shipping_address.model_dump(),
        "shipping_method_id": order_data.shipping_method_id,
        "payment_method_id": order_data.payment_method_id,
        "coupon_code": order_data.coupon_code,
        "notes": order_data.notes
    }).execute()
    
    # Create order items
    for item in order_items:
        supabase.table("order_items").insert({
            "order_id": order_id,
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "price": item["price"],
            "total": item["total"],
            "shop_id": item["shop_id"]
        }).execute()
        
        # Update product stock
        supabase.table("products").update({
            "stock": supabase.table("products").select("stock").eq("id", item["product_id"]).execute().data[0]["stock"] - item["quantity"]
        }).eq("id", item["product_id"]).execute()
    
    # Clear cart
    supabase.table("cart_items").delete().eq("user_id", current_user["id"]).execute()
    
    # Record order creation on blockchain
    try:
        order_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_CREATE,
            user_id=current_user["id"],
            data={
                "order_id": order_id,
                "total_amount": grand_total,
                "item_count": len(order_items),
                "shops_involved": list(shop_totals.keys()),
                "shipping_method": shipping_method["name"],
                "action": "order_creation"
            },
            order_id=order_id,
            metadata={
                "source": "orders_route",
                "has_coupon": bool(order_data.coupon_code),
                "shop_count": len(shop_totals)
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(order_transaction)
        
        # Update order with blockchain reference
        supabase.table("orders").update({
            "blockchain_tx_id": order_transaction.transaction_id
        }).eq("id", order_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        blockchain_tx_id = None
    
    # Background task: Send order confirmation email
    if background_tasks:
        from app.services.email_service import send_order_confirmation
        background_tasks.add_task(
            send_order_confirmation,
            user_email=current_user["email"],
            order_id=order_id,
            order_total=grand_total
        )
    
    return {
        "message": "Order created successfully",
        "order_id": order_id,
        "total": grand_total,
        "blockchain_tx_id": blockchain_tx_id
    }

@router.get("/", response_model=List[Dict[str, Any]])
async def get_orders(
    current_user: dict = Depends(get_current_user),
    status: Optional[OrderStatus] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = 0
):
    """Get user's orders"""
    query = supabase.table("orders").select(
        "*, shipping_methods(name), order_items(count)"
    ).eq("user_id", current_user["id"])
    
    if status:
        query = query.eq("status", status)
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    orders = []
    for order in result.data:
        orders.append({
            "id": order["id"],
            "total_amount": order["total_amount"],
            "status": order["status"],
            "item_count": order["order_items"][0]["count"] if order["order_items"] else 0,
            "shipping_method": order["shipping_methods"]["name"] if order["shipping_methods"] else None,
            "created_at": order["created_at"],
            "blockchain_tx_id": order.get("blockchain_tx_id")
        })
    
    return orders

@router.get("/{order_id}", response_model=Dict[str, Any])
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get order details"""
    # Get order
    order_result = supabase.table("orders").select(
        "*, shipping_methods(name, estimated_days), payment_methods(type, last_four)"
    ).eq("id", order_id).eq("user_id", current_user["id"]).execute()
    
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = order_result.data[0]
    
    # Get order items
    items_result = supabase.table("order_items").select(
        "*, products(title, images, shops(name))"
    ).eq("order_id", order_id).execute()
    
    items = []
    for item in items_result.data:
        items.append({
            "product_id": item["product_id"],
            "title": item["products"]["title"],
            "images": item["products"]["images"],
            "quantity": item["quantity"],
            "price": item["price"],
            "total": item["total"],
            "shop_name": item["products"]["shops"]["name"]
        })
    
    # Get shipping tracking if available
    tracking_result = supabase.table("order_tracking").select("*").eq(
        "order_id", order_id
    ).order("created_at", desc=True).limit(1).execute()
    
    tracking = tracking_result.data[0] if tracking_result.data else None
    
    # Get order blockchain activity
    try:
        order_transactions = blockchain_service.get_transactions_by_order(order_id)
        order["blockchain_activity"] = {
            "total_transactions": len(order_transactions),
            "recent_activity": [
                {
                    "transaction_type": tx.transaction_type,
                    "timestamp": tx.timestamp,
                    "data": tx.data
                }
                for tx in order_transactions[:5]
            ]
        }
    except Exception as e:
        print(f"Failed to get order blockchain transactions: {e}")
    
    return {
        **order,
        "items": items,
        "tracking": tracking,
        "shipping_address": json.loads(order["shipping_address"]) if isinstance(order["shipping_address"], str) else order["shipping_address"]
    }

@router.put("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    """Cancel an order"""
    # Get order
    order_result = supabase.table("orders").select("*").eq(
        "id", order_id
    ).eq("user_id", current_user["id"]).execute()
    
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = order_result.data[0]
    
    # Check if order can be cancelled
    if order["status"] not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status: {order['status']}"
        )
    
    # Update order status
    supabase.table("orders").update({
        "status": OrderStatus.CANCELLED,
        "cancelled_at": datetime.now().isoformat()
    }).eq("id", order_id).execute()
    
    # Restock products
    items_result = supabase.table("order_items").select("*").eq("order_id", order_id).execute()
    for item in items_result.data:
        supabase.table("products").update({
            "stock": supabase.table("products").select("stock").eq("id", item["product_id"]).execute().data[0]["stock"] + item["quantity"]
        }).eq("id", item["product_id"]).execute()
    
    # Record cancellation on blockchain
    try:
        cancel_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_CANCEL,
            user_id=current_user["id"],
            data={
                "order_id": order_id,
                "previous_status": order["status"],
                "total_amount": order["total_amount"],
                "action": "order_cancellation"
            },
            order_id=order_id,
            metadata={
                "source": "orders_route",
                "items_restocked": len(items_result.data),
                "user_initiated": True
            }
        )
        
        blockchain_service.add_transaction(cancel_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    # Background task: Send cancellation email
    if background_tasks:
        from app.services.email_service import send_order_cancellation
        background_tasks.add_task(
            send_order_cancellation,
            user_email=current_user["email"],
            order_id=order_id
        )
    
    return {"message": "Order cancelled successfully"}

@router.get("/{order_id}/tracking")
async def get_order_tracking(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get order tracking information"""
    # Verify order belongs to user
    order_result = supabase.table("orders").select("id").eq(
        "id", order_id
    ).eq("user_id", current_user["id"]).execute()
    
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get tracking info
    tracking_result = supabase.table("order_tracking").select("*").eq(
        "order_id", order_id
    ).order("created_at").execute()
    
    return {
        "order_id": order_id,
        "tracking": tracking_result.data
    }

@router.post("/{order_id}/return")
async def request_return(
    order_id: str,
    reason: str,
    current_user: dict = Depends(get_current_user)
):
    """Request return for an order"""
    # Get order
    order_result = supabase.table("orders").select("*").eq(
        "id", order_id
    ).eq("user_id", current_user["id"]).execute()
    
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = order_result.data[0]
    
    # Check if order can be returned
    if order["status"] != OrderStatus.DELIVERED:
        raise HTTPException(
            status_code=400,
            detail="Only delivered orders can be returned"
        )
    
    # Check if return already requested
    existing_return = supabase.table("order_returns").select("*").eq(
        "order_id", order_id
    ).execute()
    
    if existing_return.data:
        raise HTTPException(status_code=400, detail="Return already requested for this order")
    
    # Create return request
    return_id = str(uuid.uuid4())
    supabase.table("order_returns").insert({
        "id": return_id,
        "order_id": order_id,
        "user_id": current_user["id"],
        "reason": reason,
        "status": "pending",
        "requested_at": datetime.now().isoformat()
    }).execute()
    
    return {
        "message": "Return request submitted successfully",
        "return_id": return_id,
        "status": "pending"
    }

@router.get("/stats")
async def get_order_stats(current_user: dict = Depends(get_current_user)):
    """Get user order statistics"""
    # Get total orders
    total_result = supabase.table("orders").select(
        "count", count="exact"
    ).eq("user_id", current_user["id"]).execute()
    
    # Get orders by status
    status_result = supabase.table("orders").select(
        "status, count(*)"
    ).eq("user_id", current_user["id"]).group("status").execute()
    
    # Get total spent
    spent_result = supabase.table("orders").select(
        "sum(total_amount)"
    ).eq("user_id", current_user["id"]).eq("status", OrderStatus.DELIVERED).execute()
    
    status_counts = {}
    for item in status_result.data:
        status_counts[item["status"]] = item["count"]
    
    return {
        "total_orders": total_result.count or 0,
        "status_counts": status_counts,
        "total_spent": spent_result.data[0]["sum"] if spent_result.data and spent_result.data[0]["sum"] else 0,
        "average_order_value": (
            spent_result.data[0]["sum"] / total_result.count 
            if total_result.count and total_result.count > 0 and spent_result.data and spent_result.data[0]["sum"]
            else 0
        )
    }