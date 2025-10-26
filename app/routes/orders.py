from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.model.models import OrderCreate, OrderResponse, OrderStatus
from app.dependencies import get_current_user, get_current_merchant, get_current_admin

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

import stripe
from app.config import settings

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=dict)
async def create_order(order_data: OrderCreate, current_user: dict = Depends(get_current_user)):
    # Calculate total and verify product availability
    total_amount = 0
    order_items = []
    products_info = []
    
    for item in order_data.items:
        product_result = supabase.table("products").select("*, shops(name)").eq("id", item.product_id).execute()
        if not product_result.data:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        
        product = product_result.data[0]
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
        
        products_info.append({
            "product_id": product["id"],
            "title": product["title"],
            "brand": product["brand"],
            "price": product["price"],
            "shop_name": product["shops"]["name"]
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
        current_stock = supabase.table("products").select("stock").eq("id", item["product_id"]).execute().data[0]["stock"]
        new_stock = current_stock - item["quantity"]
        supabase.table("products").update({"stock": new_stock}).eq("id", item["product_id"]).execute()
    
    # Record order creation on blockchain
    try:
        order_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_CREATE,
            user_id=current_user["id"],
            data={
                "order_id": order_id,
                "shop_id": shop_id,
                "total_amount": total_amount,
                "items_count": len(order_items),
                "products": products_info,
                "shipping_address": order_data.shipping_address,
                "status": "pending",
                "action": "order_creation"
            },
            shop_id=shop_id,
            order_id=order_id,
            metadata={
                "source": "orders_route",
                "payment_required": True,
                "items_count": len(order_items)
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(order_transaction)
        
        # Update order with blockchain transaction reference
        supabase.table("orders").update({
            "blockchain_tx_id": order_transaction.transaction_id
        }).eq("id", order_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with order creation even if blockchain fails
    
    # Create Stripe payment intent
    client_secret = None
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        payment_intent = stripe.PaymentIntent.create(
            amount=int(total_amount * 100),  # Convert to cents
            currency="usd",
            metadata={
                "order_id": order_id,
                "user_id": current_user["id"],
                "blockchain_tx_id": order_transaction.transaction_id if 'order_transaction' in locals() else None
            }
        )
        client_secret = payment_intent.client_secret
    
    return {
        "order_id": order_id,
        "total_amount": total_amount,
        "client_secret": client_secret,
        "message": "Order created successfully",
        "blockchain_tx_id": order_transaction.transaction_id if 'order_transaction' in locals() else None
    }

@router.get("/", response_model=list)
async def get_user_orders(current_user: dict = Depends(get_current_user)):
    result = supabase.table("orders").select("*, order_items(*, products(*)), shops(name)").eq("user_id", current_user["id"]).execute()
    
    # Enhance with blockchain data
    orders_with_blockchain = []
    for order in result.data:
        try:
            # Get blockchain transactions for this order
            order_transactions = []
            for block in blockchain_service.blockchain.chain:
                for tx in block.transactions:
                    if tx.order_id == order["id"]:
                        order_transactions.append(tx)
            
            order["blockchain_activity_count"] = len(order_transactions)
        except Exception as e:
            print(f"Failed to get blockchain data for order {order['id']}: {e}")
            order["blockchain_activity_count"] = 0
        
        orders_with_blockchain.append(order)
    
    return orders_with_blockchain

@router.get("/{order_id}")
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    result = supabase.table("orders").select("*, order_items(*, products(*)), shops(name)").eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = result.data[0]
    if order["user_id"] != current_user["id"] and current_user["type"] != "admin":
        # Check if current user is the shop owner
        if current_user["type"] == "merchant":
            shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
            if not shop_result.data or shop_result.data[0]["id"] != order["shop_id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get order's blockchain transactions for enhanced response
    try:
        order_transactions = []
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                if tx.order_id == order_id:
                    order_transactions.append(tx)
        
        order["blockchain_activity"] = {
            "total_transactions": len(order_transactions),
            "activity": [
                {
                    "transaction_type": tx.transaction_type,
                    "timestamp": tx.timestamp,
                    "user_id": tx.user_id,
                    "data": tx.data
                }
                for tx in order_transactions
            ]
        }
    except Exception as e:
        print(f"Failed to get order blockchain transactions: {e}")
    
    return order

@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status: OrderStatus,
    current_user: dict = Depends(get_current_user)
):
    """Update order status (for merchants and admins)"""
    # Check if order exists
    order_result = supabase.table("orders").select("*, shops(user_id), users(email, name)").eq("id", order_id).execute()
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = order_result.data[0]
    old_status = order["status"]
    
    # Check permissions
    if current_user["type"] == "merchant":
        # Check if order belongs to merchant's shop
        shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
        if not shop_result.data or shop_result.data[0]["id"] != order["shop_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["type"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    if old_status == status:
        raise HTTPException(status_code=400, detail=f"Order is already {status}")
    
    # Update order status
    result = supabase.table("orders").update({"status": status}).eq("id", order_id).execute()
    
    # Record order status update on blockchain
    try:
        status_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_UPDATE,
            user_id=current_user["id"],
            data={
                "order_id": order_id,
                "customer_id": order["user_id"],
                "customer_email": order["users"]["email"],
                "shop_id": order["shop_id"],
                "previous_status": old_status,
                "new_status": status,
                "total_amount": order["total_amount"],
                "action": "order_status_update"
            },
            shop_id=order["shop_id"],
            order_id=order_id,
            metadata={
                "source": "orders_route_status",
                "updated_by": "merchant" if current_user["type"] == "merchant" else "admin",
                "status_change": f"{old_status}->{status}"
            }
        )
        
        blockchain_service.add_transaction(status_transaction)
        
        # Update order with new blockchain transaction reference
        supabase.table("orders").update({
            "blockchain_tx_id": status_transaction.transaction_id
        }).eq("id", order_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": f"Order status updated to {status}",
        "order_id": order_id,
        "previous_status": old_status,
        "new_status": status,
        "blockchain_tx_id": status_transaction.transaction_id if 'status_transaction' in locals() else None
    }

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel an order (for customers and admins)"""
    # Check if order exists
    order_result = supabase.table("orders").select("*, order_items(*, products(*))").eq("id", order_id).execute()
    if not order_result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = order_result.data[0]
    
    # Check permissions
    if current_user["type"] == "customer" and order["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order["status"] in ["delivered", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel order with status: {order['status']}")
    
    old_status = order["status"]
    
    # Update order status to cancelled
    result = supabase.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
    
    # Restore product stock
    for item in order["order_items"]:
        product = item["products"]
        current_stock = product["stock"]
        new_stock = current_stock + item["quantity"]
        supabase.table("products").update({"stock": new_stock}).eq("id", product["id"]).execute()
    
    # Record order cancellation on blockchain
    try:
        cancel_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.ORDER_CANCEL,
            user_id=current_user["id"],
            data={
                "order_id": order_id,
                "shop_id": order["shop_id"],
                "previous_status": old_status,
                "new_status": "cancelled",
                "total_amount": order["total_amount"],
                "items_restocked": len(order["order_items"]),
                "action": "order_cancellation"
            },
            shop_id=order["shop_id"],
            order_id=order_id,
            metadata={
                "source": "orders_route_cancel",
                "cancelled_by": "customer" if current_user["type"] == "customer" else "admin",
                "stock_restored": True
            }
        )
        
        blockchain_service.add_transaction(cancel_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Order cancelled successfully",
        "order_id": order_id,
        "stock_restored": True,
        "blockchain_tx_id": cancel_transaction.transaction_id if 'cancel_transaction' in locals() else None
    }

@router.get("/shop/orders")
async def get_shop_orders(current_user: dict = Depends(get_current_merchant)):
    """Get all orders for merchant's shop"""
    # Get merchant's shop
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    
    result = supabase.table("orders").select("*, order_items(*, products(*)), users(name, email)").eq("shop_id", shop_id).execute()
    
    # Enhance with blockchain data
    orders_with_blockchain = []
    for order in result.data:
        try:
            # Get blockchain transactions for this order
            order_transactions = []
            for block in blockchain_service.blockchain.chain:
                for tx in block.transactions:
                    if tx.order_id == order["id"]:
                        order_transactions.append(tx)
            
            order["blockchain_activity_count"] = len(order_transactions)
        except Exception as e:
            print(f"Failed to get blockchain data for order {order['id']}: {e}")
            order["blockchain_activity_count"] = 0
        
        orders_with_blockchain.append(order)
    
    return orders_with_blockchain

@router.get("/{order_id}/blockchain-activity")
async def get_order_blockchain_activity(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed blockchain activity for a specific order"""
    try:
        # Check if order exists and user has access
        order_result = supabase.table("orders").select("*, shops(name), users(name, email)").eq("id", order_id).execute()
        if not order_result.data:
            raise HTTPException(status_code=404, detail="Order not found")
        
        order = order_result.data[0]
        
        # Check access rights
        if (current_user["type"] == "customer" and order["user_id"] != current_user["id"]) and \
           (current_user["type"] == "merchant" and order["shop_id"] != supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute().data[0]["id"]) and \
           current_user["type"] != "admin":
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get all transactions for this order
        all_transactions = []
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                if tx.order_id == order_id:
                    all_transactions.append(tx)
        
        # Also check pending transactions
        for tx in blockchain_service.blockchain.pending_transactions:
            if tx.order_id == order_id:
                all_transactions.append(tx)
        
        # Format response
        activity = []
        for tx in all_transactions:
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
                "shop_id": tx.shop_id,
                "product_id": tx.product_id
            })
        
        return {
            "order_id": order_id,
            "customer_name": order["users"]["name"],
            "shop_name": order["shops"]["name"],
            "total_amount": order["total_amount"],
            "current_status": order["status"],
            "total_activities": len(activity),
            "activity": sorted(activity, key=lambda x: x["timestamp"], reverse=True)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to retrieve blockchain activity: {str(e)}"
        )