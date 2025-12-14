from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List, Dict, Any
import json
from app.database import supabase
from app.model.models import CategoryCreate, CategoryResponse, CategoryUpdate, ProductCategoryAssignment
from app.dependencies import get_current_admin, get_current_merchant, get_current_user
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

router = APIRouter(prefix="/categories", tags=["categories"])

# ========== ADMIN ENDPOINTS ==========

@router.post("/", response_model=Dict[str, Any])
async def create_category(
    category_data: CategoryCreate,
    current_user: dict = Depends(get_current_admin)
):
    """
    Create a new category (Admin only)
    """
    # Check if slug already exists
    if category_data.slug:
        existing = supabase.table("categories").select("*").eq("slug", category_data.slug).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Slug already exists")
    
    # Check parent exists if specified
    if category_data.parent_id:
        parent = supabase.table("categories").select("*").eq("id", category_data.parent_id).execute()
        if not parent.data:
            raise HTTPException(status_code=404, detail="Parent category not found")
    
    # Create category
    category_dict = category_data.dict(exclude_unset=True)
    result = supabase.table("categories").insert(category_dict).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create category"
        )
    
    category_id = result.data[0]["id"]
    
    # Record on blockchain
    try:
        category_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.CATEGORY_CREATE,
            user_id=current_user["id"],
            data={
                "category_id": category_id,
                "category_name": category_data.name,
                "description": category_data.description,
                "parent_id": category_data.parent_id,
                "action": "category_creation"
            },
            metadata={
                "source": "categories_route",
                "has_parent": bool(category_data.parent_id),
                "has_icon": bool(category_data.icon)
            }
        )
        
        blockchain_tx_id = blockchain_service.add_transaction(category_transaction)
        
        # Update category with blockchain reference
        supabase.table("categories").update({
            "blockchain_tx_id": category_transaction.transaction_id
        }).eq("id", category_id).execute()
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
        # Continue even if blockchain fails
    
    return {
        "message": "Category created successfully",
        "category_id": category_id,
        "blockchain_tx_id": category_transaction.transaction_id if 'category_transaction' in locals() else None
    }

@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    include_products_count: bool = Query(False, description="Include product count for each category"),
    parent_id: Optional[str] = Query(None, description="Filter by parent category"),
    limit: int = Query(100, le=200),
    offset: int = 0
):
    """
    Get all categories (Public)
    """
    query = supabase.table("categories").select("*", count="exact")
    
    if parent_id:
        query = query.eq("parent_id", parent_id)
    else:
        query = query.is_("parent_id", "null")  # Get root categories
    
    result = query.order("name").range(offset, offset + limit - 1).execute()
    
    categories = []
    for category in result.data:
        # Get product count if requested
        product_count = 0
        if include_products_count:
            count_result = supabase.table("product_categories").select(
                "count", count="exact"
            ).eq("category_id", category["id"]).execute()
            product_count = count_result.count or 0
        
        # Get children recursively
        children = await get_child_categories(category["id"], include_products_count)
        
        categories.append({
            **category,
            "product_count": product_count,
            "children": children
        })
    
    return categories

async def get_child_categories(parent_id: str, include_products_count: bool = False) -> List[Dict]:
    """
    Helper function to get child categories recursively
    """
    result = supabase.table("categories").select("*").eq("parent_id", parent_id).order("name").execute()
    
    children = []
    for child in result.data:
        product_count = 0
        if include_products_count:
            count_result = supabase.table("product_categories").select(
                "count", count="exact"
            ).eq("category_id", child["id"]).execute()
            product_count = count_result.count or 0
        
        # Recursively get grandchildren
        grandchildren = await get_child_categories(child["id"], include_products_count)
        
        children.append({
            **child,
            "product_count": product_count,
            "children": grandchildren
        })
    
    return children

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: str, include_products_count: bool = Query(False)):
    """
    Get single category with details (Public)
    """
    result = supabase.table("categories").select("*").eq("id", category_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category = result.data[0]
    
    # Get product count if requested
    product_count = 0
    if include_products_count:
        count_result = supabase.table("product_categories").select(
            "count", count="exact"
        ).eq("category_id", category_id).execute()
        product_count = count_result.count or 0
    
    # Get children
    children = await get_child_categories(category_id, include_products_count)
    
    return {
        **category,
        "product_count": product_count,
        "children": children
    }

@router.put("/{category_id}")
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_user: dict = Depends(get_current_admin)
):
    """
    Update category (Admin only)
    """
    # Check if category exists
    existing = supabase.table("categories").select("*").eq("id", category_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Category not found")
    
    old_category = existing.data[0]
    
    # Check if new slug already exists (if being changed)
    if category_data.slug and category_data.slug != old_category.get("slug"):
        slug_check = supabase.table("categories").select("*").eq("slug", category_data.slug).neq("id", category_id).execute()
        if slug_check.data:
            raise HTTPException(status_code=400, detail="Slug already exists")
    
    # Check parent exists (if being changed)
    if category_data.parent_id and category_data.parent_id != old_category.get("parent_id"):
        # Prevent circular reference
        if category_data.parent_id == category_id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")
        
        # Check parent exists
        parent = supabase.table("categories").select("*").eq("id", category_data.parent_id).execute()
        if not parent.data:
            raise HTTPException(status_code=404, detail="Parent category not found")
    
    # Update category
    update_dict = category_data.dict(exclude_unset=True)
    result = supabase.table("categories").update(update_dict).eq("id", category_id).execute()
    
    # Record on blockchain
    try:
        changed_fields = []
        for field in ["name", "description", "icon", "slug", "parent_id"]:
            if field in update_dict and update_dict[field] != old_category.get(field):
                changed_fields.append(field)
        
        update_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.CATEGORY_UPDATE,
            user_id=current_user["id"],
            data={
                "category_id": category_id,
                "category_name": update_dict.get("name", old_category["name"]),
                "changed_fields": changed_fields,
                "previous_data": {field: old_category.get(field) for field in changed_fields},
                "new_data": {field: update_dict.get(field) for field in changed_fields},
                "action": "category_update"
            },
            metadata={
                "source": "categories_route_update",
                "has_parent_change": "parent_id" in changed_fields
            }
        )
        
        blockchain_service.add_transaction(update_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Category updated successfully",
        "category_id": category_id
    }

@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    current_user: dict = Depends(get_current_admin)
):
    """
    Delete category (Admin only)
    Note: Cannot delete if category has products or children
    """
    # Check if category exists
    existing = supabase.table("categories").select("*").eq("id", category_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category = existing.data[0]
    
    # Check if category has children
    children = supabase.table("categories").select("*").eq("parent_id", category_id).execute()
    if children.data:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with subcategories. Delete or move children first."
        )
    
    # Check if category has products
    products = supabase.table("product_categories").select("*").eq("category_id", category_id).execute()
    if products.data:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with assigned products. Remove products first."
        )
    
    # Record deletion on blockchain
    try:
        delete_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.CATEGORY_DELETE,
            user_id=current_user["id"],
            data={
                "category_id": category_id,
                "category_name": category["name"],
                "action": "category_deletion"
            },
            metadata={
                "source": "categories_route_delete",
                "permanent_deletion": True
            }
        )
        
        blockchain_service.add_transaction(delete_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    # Delete category
    result = supabase.table("categories").delete().eq("id", category_id).execute()
    
    return {
        "message": "Category deleted successfully",
        "category_id": category_id,
        "category_name": category["name"]
    }

# ========== PRODUCT-CATEGORY ASSIGNMENT ==========

@router.post("/products/{product_id}/assign")
async def assign_categories_to_product(
    product_id: str,
    assignment: ProductCategoryAssignment,
    current_user: dict = Depends(get_current_merchant)
):
    """
    Assign categories to a product (Merchant only)
    """
    # Verify product ownership
    product_result = supabase.table("products").select("*, shops(name)").eq("id", product_id).execute()
    if not product_result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data or product_result.data[0]["shop_id"] != shop_result.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    product = product_result.data[0]
    shop_id = shop_result.data[0]["id"]
    
    # Check all categories exist
    for category_id in assignment.category_ids:
        category = supabase.table("categories").select("*").eq("id", category_id).execute()
        if not category.data:
            raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
    
    # Get existing assignments
    existing_result = supabase.table("product_categories").select("*").eq("product_id", product_id).execute()
    existing_categories = [item["category_id"] for item in existing_result.data]
    
    # Determine changes
    categories_to_add = [cid for cid in assignment.category_ids if cid not in existing_categories]
    categories_to_remove = [cid for cid in existing_categories if cid not in assignment.category_ids]
    
    # Perform updates
    if categories_to_remove:
        supabase.table("product_categories").delete().eq("product_id", product_id).in_("category_id", categories_to_remove).execute()
    
    if categories_to_add:
        new_assignments = [{"product_id": product_id, "category_id": cid} for cid in categories_to_add]
        supabase.table("product_categories").insert(new_assignments).execute()
    
    # Update primary category (first in list)
    if assignment.category_ids:
        supabase.table("products").update({"category_id": assignment.category_ids[0]}).eq("id", product_id).execute()
    else:
        supabase.table("products").update({"category_id": None}).eq("id", product_id).execute()
    
    # Record on blockchain
    try:
        assign_transaction = blockchain_service.create_transaction(
            transaction_type=TransactionType.PRODUCT_CATEGORY_UPDATE,
            user_id=current_user["id"],
            data={
                "product_id": product_id,
                "product_title": product["title"],
                "shop_id": shop_id,
                "shop_name": product["shops"]["name"],
                "categories_added": categories_to_add,
                "categories_removed": categories_to_remove,
                "new_categories": assignment.category_ids,
                "action": "product_category_assignment"
            },
            shop_id=shop_id,
            product_id=product_id,
            metadata={
                "source": "categories_route_assign",
                "total_categories": len(assignment.category_ids),
                "added_count": len(categories_to_add),
                "removed_count": len(categories_to_remove)
            }
        )
        
        blockchain_service.add_transaction(assign_transaction)
        
    except Exception as e:
        print(f"Blockchain transaction failed: {e}")
    
    return {
        "message": "Categories assigned successfully",
        "product_id": product_id,
        "added": categories_to_add,
        "removed": categories_to_remove,
        "current_categories": assignment.category_ids
    }

@router.get("/products/{product_id}")
async def get_product_categories(product_id: str):
    """
    Get categories for a specific product (Public)
    """
    result = supabase.table("product_categories").select("category_id, categories(name, icon, slug)").eq(
        "product_id", product_id
    ).execute()
    
    categories = []
    for item in result.data:
        categories.append({
            "category_id": item["category_id"],
            "name": item["categories"]["name"],
            "icon": item["categories"].get("icon"),
            "slug": item["categories"].get("slug")
        })
    
    return {
        "product_id": product_id,
        "categories": categories,
        "total": len(categories)
    }

@router.get("/{category_id}/products")
async def get_products_by_category(
    category_id: str,
    limit: int = Query(20, le=100),
    offset: int = 0
):
    """
    Get all products in a category (Public)
    """
    # Check if category exists
    category = supabase.table("categories").select("*").eq("id", category_id).execute()
    if not category.data:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Get product IDs from product_categories table
    product_categories = supabase.table("product_categories").select("product_id").eq(
        "category_id", category_id
    ).range(offset, offset + limit - 1).execute()
    
    product_ids = [item["product_id"] for item in product_categories.data]
    
    if not product_ids:
        return {
            "category_id": category_id,
            "category_name": category.data[0]["name"],
            "products": [],
            "total": 0
        }
    
    # Get product details
    products_result = supabase.table("products").select("*, shops(name, verified)").in_(
        "id", product_ids
    ).execute()
    
    products = []
    for product in products_result.data:
        if product.get("specs"):
            product["specs"] = json.loads(product["specs"])
        products.append(product)
    
    # Get total count
    total_result = supabase.table("product_categories").select("count", count="exact").eq(
        "category_id", category_id
    ).execute()
    
    return {
        "category_id": category_id,
        "category_name": category.data[0]["name"],
        "products": products,
        "total": total_result.count or 0,
        "offset": offset,
        "limit": limit
    }