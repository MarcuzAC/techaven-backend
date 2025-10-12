from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Optional, List
import json
from app.database import supabase
from app.models import ProductCreate, ProductResponse
from app.dependencies import get_current_merchant, get_current_user
from app.utils.storage import upload_product_image, get_image_url

router = APIRouter(prefix="/products", tags=["products"])

@router.post("/", response_model=dict)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_merchant)
):
    # Get user's shop
    shop_result = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop_result.data:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    shop_id = shop_result.data[0]["id"]
    product_dict = product_data.dict()
    product_dict["shop_id"] = shop_id
    
    if product_dict["specs"]:
        product_dict["specs"] = json.dumps(product_dict["specs"])
    
    result = supabase.table("products").insert(product_dict).execute()
    return {"message": "Product created successfully", "product_id": result.data[0]["id"]}

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    result = supabase.table("products").select("*").eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = result.data[0]
    if product.get("specs"):
        product["specs"] = json.loads(product["specs"])
    
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
    query = supabase.table("products").select("*")
    
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
        products.append(product)
    
    return products

@router.post("/{product_id}/images")
async def upload_product_images(
    product_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_merchant)
):
    # Verify product ownership
    product = supabase.table("products").select("shop_id").eq("id", product_id).execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop = supabase.table("shops").select("id").eq("user_id", current_user["id"]).execute()
    if not shop.data or product.data[0]["shop_id"] != shop.data[0]["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    image_urls = []
    for file in files:
        if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        content = await file.read()
        filename = await upload_product_image(content, file.filename)
        image_urls.append(get_image_url(filename))
    
    # Update product with new images
    supabase.table("products").update({"images": image_urls}).eq("id", product_id).execute()
    
    return {"message": "Images uploaded successfully", "image_urls": image_urls}