from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Optional, List
import json
from app.database import supabase
from app.model.models import ProductCreate, ProductResponse, ProductUpdate
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
    
    # Prepare product data
    product_dict = product_data.model_dump(exclude={"category_ids", "images"})
    product_dict["shop_id"] = shop_id
    
    if product_dict.get("specs"):
        product_dict["specs"] = json.dumps(product_dict["specs"])
    
    # Add images if provided
    if hasattr(product_data, 'images') and product_data.images:
        product_dict["images"] = product_data.images
    
    # Create product
    result = supabase.table("products").insert(product_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )
    
    product_id = result.data[0]["id"]
    
    # Handle category assignment if provided
    if product_data.category_ids:
        # Verify all categories exist
        for category_id in product_data.category_ids:
            category_check = supabase.table("categories").select("id").eq("id", category_id).execute()
            if not category_check.data:
                # Rollback product creation if category doesn't exist
                supabase.table("products").delete().eq("id", product_id).execute()
                raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
        
        # Assign categories to product
        for category_id in product_data.category_ids:
            supabase.table("product_categories").insert({
                "product_id": product_id,
                "category_id": category_id
            }).execute()
        
        # Set primary category (first in list)
        supabase.table("products").update({
            "category_id": product_data.category_ids[0]
        }).eq("id", product_id).execute()
    
    # Record product creation on blockchain
    blockchain_tx_id = None
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
                "category_ids": product_data.category_ids if product_data.category_ids else [],
                "action": "product_creation"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route",
                "initial_stock": product_data.stock,
                "has_specs": bool(product_data.specs),
                "has_categories": bool(product_data.category_ids),
                "category_count": len(product_data.category_ids) if product_data.category_ids else 0
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
        "category_ids": product_data.category_ids if product_data.category_ids else [],
        "blockchain_tx_id": blockchain_tx_id
    }

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    result = supabase.table("products").select("*, shops(name, verified)").eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = result.data[0]
    if product.get("specs"):
        product["specs"] = json.loads(product["specs"])
    
    # Get product categories
    categories_result = supabase.table("product_categories").select(
        "category_id, categories(*)"
    ).eq("product_id", product_id).execute()
    
    product["categories"] = [item["categories"] for item in categories_result.data]
    
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
                    "data": {k: v for k, v in tx.data.items() if k not in ['product_title', 'brand']}
                }
                for tx in product_transactions[:5]
            ]
        }
    except Exception as e:
        print(f"Failed to get product blockchain transactions: {e}")
    
    return product

@router.get("/", response_model=dict)
async def get_products(
    search: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    condition: Optional[str] = Query(None),
    shop_id: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
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
    if category_id:
        # Get product IDs in this category
        category_products = supabase.table("product_categories").select(
            "product_id"
        ).eq("category_id", category_id).execute()
        
        product_ids = [item["product_id"] for item in category_products.data]
        if product_ids:
            query = query.in_("id", product_ids)
        else:
            # If no products in category, return empty result
            return {
                "data": [],
                "pagination": {
                    "total": 0,
                    "offset": offset,
                    "limit": limit
                }
            }
    
    result = query.range(offset, offset + limit - 1).execute()
    
    products = []
    for product in result.data:
        if product.get("specs"):
            product["specs"] = json.loads(product["specs"])
        
        # Get categories for each product
        categories_result = supabase.table("product_categories").select(
            "category_id, categories(name, icon)"
        ).eq("product_id", product["id"]).execute()
        
        product["categories"] = [item["categories"] for item in categories_result.data]
        
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
    blockchain_tx_id = None
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
        
        blockchain_tx_id = blockchain_service.add_transaction(image_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Images uploaded successfully", 
        "image_urls": image_urls,
        "blockchain_tx_id": blockchain_tx_id
    }

@router.put("/{product_id}")
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
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
    
    # Prepare update data (exclude None values)
    update_dict = product_data.model_dump(exclude_unset=True, exclude={"category_ids"})
    
    if update_dict.get("specs"):
        update_dict["specs"] = json.dumps(update_dict["specs"])
    
    # Update product in database if there are changes
    if update_dict:
        result = supabase.table("products").update(update_dict).eq("id", product_id).execute()
    
    # Handle category updates if provided
    if product_data.category_ids is not None:
        # Get existing categories
        existing_result = supabase.table("product_categories").select("*").eq("product_id", product_id).execute()
        existing_categories = [item["category_id"] for item in existing_result.data]
        
        # Determine changes
        categories_to_add = [cid for cid in product_data.category_ids if cid not in existing_categories]
        categories_to_remove = [cid for cid in existing_categories if cid not in product_data.category_ids]
        
        # Perform updates
        if categories_to_remove:
            supabase.table("product_categories").delete().eq("product_id", product_id).in_("category_id", categories_to_remove).execute()
        
        if categories_to_add:
            new_assignments = [{"product_id": product_id, "category_id": cid} for cid in categories_to_add]
            supabase.table("product_categories").insert(new_assignments).execute()
        
        # Update primary category
        if product_data.category_ids:
            supabase.table("products").update({"category_id": product_data.category_ids[0]}).eq("id", product_id).execute()
        else:
            supabase.table("products").update({"category_id": None}).eq("id", product_id).execute()
    
    # Record product update on blockchain
    blockchain_tx_id = None
    try:
        # Identify changed fields
        changed_fields = []
        price_changed = old_product["price"] != product_data.price if product_data.price is not None else False
        stock_changed = old_product["stock"] != product_data.stock if product_data.stock is not None else False
        
        if price_changed:
            changed_fields.append("price")
        if stock_changed:
            changed_fields.append("stock")
        if product_data.title is not None and old_product["title"] != product_data.title:
            changed_fields.append("title")
        if product_data.description is not None and old_product["description"] != product_data.description:
            changed_fields.append("description")
        if product_data.brand is not None and old_product["brand"] != product_data.brand:
            changed_fields.append("brand")
        if product_data.condition is not None and old_product["condition"] != product_data.condition:
            changed_fields.append("condition")
        
        # Add category changes if applicable
        if product_data.category_ids is not None:
            changed_fields.append("categories")
        
        if changed_fields:  # Only record if something changed
            update_transaction = blockchain_service.create_transaction(
                transaction_type=TransactionType.PRODUCT_UPDATE,
                user_id=current_user["id"],
                data={
                    "product_id": product_id,
                    "product_title": product_data.title or old_product["title"],
                    "shop_id": shop_id,
                    "shop_name": old_product["shops"]["name"],
                    "changed_fields": changed_fields,
                    "previous_data": {
                        "price": old_product["price"],
                        "stock": old_product["stock"],
                        "title": old_product["title"],
                        "description": old_product["description"],
                        "brand": old_product["brand"],
                        "condition": old_product["condition"],
                        "category_ids": existing_categories if 'existing_categories' in locals() else []
                    },
                    "new_data": product_data.model_dump(exclude_unset=True),
                    "action": "product_update"
                },
                shop_id=shop_id,
                product_id=product_id,
                metadata={
                    "source": "products_route_update",
                    "price_changed": price_changed,
                    "stock_changed": stock_changed,
                    "category_changed": product_data.category_ids is not None
                }
            )
            
            blockchain_tx_id = blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Product updated successfully",
        "product_id": product_id,
        "changed_fields": changed_fields if 'changed_fields' in locals() else [],
        "blockchain_tx_id": blockchain_tx_id
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
    blockchain_tx_id = None
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
        
        blockchain_tx_id = blockchain_service.add_transaction(stock_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Stock updated successfully",
        "product_id": product_id,
        "previous_stock": old_stock,
        "new_stock": new_stock,
        "change": stock_change,
        "blockchain_tx_id": blockchain_tx_id
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
    
    # Get product categories before deletion for blockchain record
    categories_result = supabase.table("product_categories").select("category_id").eq("product_id", product_id).execute()
    category_ids = [item["category_id"] for item in categories_result.data]
    
    # Record product deletion on blockchain
    blockchain_tx_id = None
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
                "categories": category_ids,
                "action": "product_deletion"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "products_route_delete",
                "permanent_deletion": True,
                "category_count": len(category_ids)
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(delete_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    # Delete product categories first (due to foreign key constraints)
    supabase.table("product_categories").delete().eq("product_id", product_id).execute()
    
    # Delete the product
    result = supabase.table("products").delete().eq("id", product_id).execute()
    
    return {
        "message": "Product deleted successfully",
        "product_id": product_id,
        "product_title": product["title"],
        "blockchain_tx_id": blockchain_tx_id
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