from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Optional, List
import json
from app.database import supabase
from app.model.models import ProductCreate, ProductResponse
from app.dependencies import get_current_merchant, get_current_user, get_current_admin

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType
from app.utils.storage import get_image_url, upload_product_image

router = APIRouter(prefix="/products", tags=["products"])

@router.post("/", response_model=dict)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_merchant)
):
    # Get user's shop
    shop_result = supabase.table("shops").select("id, name").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    shop_name = shop_result.data[0]["name"]
    product_dict = product_data.dict()
    product_dict["shop_id"] = shop_id
    
    if product_dict["specs"]:
        product_dict["specs"] = json.dumps(product_dict["specs"])
    
    result = supabase.table("products").insert(product_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )
    
    product_id = result.data[0]["id"]
    
    # Record product creation on blockchain
    try:
        product_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PRODUCT_CREATE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product_data.title,
                "brand": product_data.brand,
                "price": product_data.price,
                "condition": product_data.condition,
                "stock": product_data.stock,
                "shop_id": shop_id,
                "shop_name": shop_name,
                "specs": product_data.specs,
                "action": "product_creation"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route",
                "initial_stock": product_data.stock,
                "has_specs": bool(product_data.specs)
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(product_transaction)
        
        # Update product with blockchain transaction reference
        supabase.table("products").update({
            "blockchain_tx_id": product_transaction.transaction_id
        }).eq("id", product_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue with product creation even if blockchain fails
    
    return {
        "message": "Product created successfully", 
        "product_id": product_id,
        "blockchain_tx_id": product_transaction.transaction_id if 'product_transaction' in locals() else None
    }

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    result = supabase.table("products").select("*, shops(name, verified)").eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = result.data[0]
    if product.get("specs"):
        product["specs"] = json.loads(product["specs"])
    
    # Get product's blockchain transactions for enhanced response
    try:
        product_transactions = blockchain_service.get_transactions_by_product(product_id)
        product["blockchain_activity"] = {
            "total_transactions": len(product_transactions),
            "recent_activity": [
                {
                    "transaction_type": tx.transaction_type,
                    "timestamp": tx.timestamp,
                    "user_id": tx.user_id,
                    "data": {k: v for k, v in tx.data.items() if k not in ['product_title', 'brand']}  # Exclude redundant info
                }
                for tx in product_transactions[:5]  # Last 5 transactions
            ]
        }
    except Exception as e:
        print(f"Failed to get product blockchain transactions: {e}")
    
    return product

@router.get("/", response_model=List[ProductResponse])
async def get_products(
    search: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    condition: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = 0
):
    query = supabase.table("products").select("*, shops(name, verified)", count="exact")
    
    if search:
        query = query.ilike("title", f"%{search}%")
    if brand:
        query = query.eq("brand", brand)
    if min_price is not None:
        query = query.gte("price", min_price)
    if max_price is not None:
        query = query.lte("price", max_price)
    if condition:
        query = query.eq("condition", condition)
    if shop_id:
        query = query.eq("shop_id", shop_id)
    
    result = query.range(offset, offset + limit - 1).execute()
    
    products = []
    for product in result.data:
        if product.get("specs"):
            product["specs"] = json.loads(product["specs"])
        
        # Add blockchain transaction count
        try:
            product_transactions = blockchain_service.get_transactions_by_product(product["id"])
            product["blockchain_transaction_count"] = len(product_transactions)
        except Exception as e:
            print(f"Failed to get blockchain data for product {product['id']}: {e}")
            product["blockchain_transaction_count"] = 0
        
        products.append(product)
    
    return {
        "data": products,
        "pagination": {
            "total": result.count,
            "offset": offset,
            "limit": limit
        }
    }

@router.post("/{product_id}/images")
async def upload_product_images(
    product_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_merchant)
):
    # Verify product ownership
    product_result = supabase.table("products").select("shop_id, title").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop_result = supabase.table("shops").select("id, name").eq("user_id", current_user["id"]).execute()
    if not shop_result.data or product_result.data[0]["shop_id"] != shop_result.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    product = product_result.data[0]
    shop = shop_result.data[0]
    
    image_urls = []
    for file in files:
        if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        content = await file.read()
        filename = await upload_product_image(content, file.filename)
        image_urls.append(get_image_url(filename))
    
    # Update product with new images
    supabase.table("products").update({"images": image_urls}).eq("id", product_id).execute()
    
    # Record image upload on blockchain
    try:
        image_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PRODUCT_UPDATE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product["title"],
                "shop_id": shop["id"],
                "shop_name": shop["name"],
                "images_uploaded": len(image_urls),
                "image_urls": image_urls,
                "action": "product_images_upload"
            },
            shop_id=shop["id"],
            product_id=product_id,
            metadata={
                "source": "products_route_images",
                "file_count": len(files),
                "file_types": [file.content_type for file in files]
            }
        )
        
        blockchain_service.add_transaction(image_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Images uploaded successfully", 
        "image_urls": image_urls,
        "blockchain_tx_id": image_transaction.transaction_id if 'image_transaction' in locals() else None
    }

@router.put("/{product_id}")
async def update_product(
    product_id: str,
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_merchant)
):
    """Update product details"""
    # Verify product ownership
    product_result = supabase.table("products").select("*, shops(name)").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data or product_result.data[0]["shop_id"] != shop_result.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    old_product = product_result.data[0]
    shop_id = shop_result.data[0]["id"]
    
    # Prepare update data
    update_dict = product_data.dict()
    if update_dict["specs"]:
        update_dict["specs"] = json.dumps(update_dict["specs"])
    
    # Update product in database
    result = supabase.table("products").update(update_dict).eq("id", product_id).execute()
    
    # Record product update on blockchain
    try:
        # Identify changed fields
        changed_fields = []
        price_changed = old_product["price"] != product_data.price
        stock_changed = old_product["stock"] != product_data.stock
        
        if price_changed:
            changed_fields.append("price")
        if stock_changed:
            changed_fields.append("stock")
        if old_product["title"] != product_data.title:
            changed_fields.append("title")
        if old_product["description"] != product_data.description:
            changed_fields.append("description")
        if old_product["brand"] != product_data.brand:
            changed_fields.append("brand")
        if old_product["condition"] != product_data.condition:
            changed_fields.append("condition")
        
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PRODUCT_UPDATE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product_data.title,
                "shop_id": shop_id,
                "shop_name": old_product["shops"]["name"],
                "changed_fields": changed_fields,
                "previous_data": {
                    "price": old_product["price"],
                    "stock": old_product["stock"],
                    "title": old_product["title"],
                    "description": old_product["description"],
                    "brand": old_product["brand"],
                    "condition": old_product["condition"]
                },
                "new_data": product_data.dict(),
                "action": "product_update"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route_update",
                "price_changed": price_changed,
                "stock_changed": stock_changed
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Product updated successfully",
        "product_id": product_id,
        "blockchain_tx_id": update_transaction.transaction_id if 'update_transaction' in locals() else None
    }

@router.patch("/{product_id}/stock")
async def update_product_stock(
    product_id: str,
    stock_change: int,
    current_user: dict = Depends(get_current_merchant)
):
    """Update product stock (increment/decrement)"""
    # Verify product ownership
    product_result = supabase.table("products").select("*, shops(name)").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data or product_result.data[0]["shop_id"] != shop_result.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    product = product_result.data[0]
    shop_id = shop_result.data[0]["id"]
    old_stock = product["stock"]
    new_stock = max(0, old_stock + stock_change)  # Prevent negative stock
    
    # Update stock in database
    result = supabase.table("products").update({"stock": new_stock}).eq("id", product_id).execute()
    
    # Record stock update on blockchain
    try:
        stock_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.STOCK_UPDATE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product["title"],
                "shop_id": shop_id,
                "shop_name": product["shops"]["name"],
                "previous_stock": old_stock,
                "stock_change": stock_change,
                "new_stock": new_stock,
                "action": "stock_update"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route_stock",
                "operation": "increment" if stock_change > 0 else "decrement",
                "absolute_change": abs(stock_change)
            }
        )
        
        blockchain_service.add_transaction(stock_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Stock updated successfully",
        "product_id": product_id,
        "previous_stock": old_stock,
        "new_stock": new_stock,
        "change": stock_change,
        "blockchain_tx_id": stock_transaction.transaction_id if 'stock_transaction' in locals() else None
    }

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_merchant)
):
    """Delete a product"""
    # Verify product ownership
    product_result = supabase.table("products").select("*, shops(name)").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data or product_result.data[0]["shop_id"] != shop_result.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    product = product_result.data[0]
    shop_id = shop_result.data[0]["id"]
    
    # Record product deletion on blockchain
    try:
        delete_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PRODUCT_DELETE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product["title"],
                "shop_id": shop_id,
                "shop_name": product["shops"]["name"],
                "brand": product["brand"],
                "price": product["price"],
                "stock_at_deletion": product["stock"],
                "action": "product_deletion"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route_delete",
                "permanent_deletion": True
            }
        )
        
        blockchain_service.add_transaction(delete_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    # Delete the product
    result = supabase.table("products").delete().eq("id", product_id).execute()
    
    return {
        "message": "Product deleted successfully",
        "product_id": product_id,
        "product_title": product["title"],
        "blockchain_tx_id": delete_transaction.transaction_id if 'delete_transaction' in locals() else None
    }

@router.get("/{product_id}/blockchain-activity")
async def get_product_blockchain_activity(
    product_id: str,
    limit: int = 50,
    transaction_type: str = None
):
    """Get detailed blockchain activity for a specific product"""
    try:
        # Check if product exists
        product_result = supabase.table("products").select("id, title, shops(name)").eq("id", product_id).execute()
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = product_result.data[0]
        
        # Get product transactions
        all_transactions = blockchain_service.get_transactions_by_product(product_id)
        
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
                "user_id": tx.user_id,
                "timestamp": tx.timestamp,
                "data": tx.data,
                "metadata": tx.metadata,
                "confirmed": confirmed,
                "block_index": block_index,
                "shop_id": tx.shop_id,
                "order_id": tx.order_id
            })
        
        return {
            "product_id": product_id,
            "product_title": product["title"],
            "shop_name": product["shops"]["name"],
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