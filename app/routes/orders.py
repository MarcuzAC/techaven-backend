from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.models import OrderCreate, OrderResponse
from app.dependencies import get_current_user
import stripe
from app.config import settings

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=dict)
async def create_order(order_data: OrderCreate, current_user: dict = Depends(get_current_user)):
    # Calculate total and verify product availability
    total_amount = 0
    order_items = []
    
    for item in order_data.items:
        product = supabase.table("products").select("*").eq("id", item.product_id).execute()
        if not product.data:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        
        product = product.data[0]
        if product["stock"] < item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Not enough stock for product {product['title']}"
            )
        
        item_total = product["price"] * item.quantity
        total_amount += item_total
        
        order_items.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": product["price"],
            "total_price": item_total
        })
    
    # Get shop_id from first product
    first_product = supabase.table("products").select("shop_id").eq("id", order_data.items[0].product_id).execute()
    shop_id = first_product.data[0]["shop_id"]
    
    # Create order
    order_data_dict = {
        "user_id": current_user["id"],
        "shop_id": shop_id,
        "total_amount": total_amount,
        "status": "pending",
        "shipping_address": order_data.shipping_address
    }
    
    order_result = supabase.table("orders").insert(order_data_dict).execute()
    order_id = order_result.data[0]["id"]
    
    # Create order items and update stock
    for item in order_items:
        order_item = {
            "order_id": order_id,
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"]
        }
        supabase.table("order_items").insert(order_item).execute()
        
        # Update product stock
        supabase.table("products").update({
            "stock": supabase.table("products").select("stock").eq("id", item["product_id"]).execute().data[0]["stock"] - item["quantity"]
        }).eq("id", item["product_id"]).execute()
    
    # Create Stripe payment intent
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        payment_intent = stripe.PaymentIntent.create(
            amount=int(total_amount * 100),  # Convert to cents
            currency="usd",
            metadata={"order_id": order_id}
        )
        
        return {
            "order_id": order_id,
            "total_amount": total_amount,
            "client_secret": payment_intent.client_secret,
            "message": "Order created successfully"
        }
    
    return {"order_id": order_id, "total_amount": total_amount, "message": "Order created successfully"}

@router.get("/", response_model=list)
async def get_user_orders(current_user: dict = Depends(get_current_user)):
    result = supabase.table("orders").select("*, order_items(*, products(*))").eq("user_id", current_user["id"]).execute()
    return result.data

@router.get("/{order_id}")
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    result = supabase.table("orders").select("*, order_items(*, products(*))").eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = result.data[0]
    if order["user_id"] != current_user["id"] and current_user["type"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    return order