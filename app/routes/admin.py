from fastapi import APIRouter, Depends, HTTPException, status
from app.database import supabase
from app.dependencies import get_current_admin
from datetime import datetime, timedelta

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/metrics")
async def get_admin_metrics(current_user: dict = Depends(get_current_admin)):
    try:
        # Get basic platform metrics
        total_users = supabase.table("users").select("id", count="exact").execute()
        total_shops = supabase.table("shops").select("id", count="exact").execute()
        total_products = supabase.table("products").select("id", count="exact").execute()
        total_orders = supabase.table("orders").select("id", count="exact").execute()
        pending_shops = supabase.table("shops").select("id", count="exact").eq("verified", False).execute()
        
        # Calculate total revenue from orders
        orders_data = supabase.table("orders").select("total_amount").execute()
        total_revenue = sum(order.get('total_amount', 0) for order in (orders_data.data or []))
        
        # Generate monthly data for charts
        monthly_data = generate_monthly_data()
        
        # Calculate growth percentages
        user_growth = calculate_growth(monthly_data, 'users')
        product_growth = calculate_growth(monthly_data, 'products')
        order_growth = calculate_growth(monthly_data, 'orders')
        shop_growth = calculate_growth(monthly_data, 'shops')
        
        return {
            "data": {
                "totalUsers": total_users.count or 0,
                "totalShops": total_shops.count or 0,
                "totalProducts": total_products.count or 0,
                "totalOrders": total_orders.count or 0,
                "totalRevenue": total_revenue,
                "pendingShops": pending_shops.count or 0,
                "userGrowth": user_growth,
                "productGrowth": product_growth,
                "orderGrowth": order_growth,
                "shopGrowth": shop_growth,
                "revenueGrowth": order_growth,
                "monthlyData": monthly_data,
                "categoryDistribution": []
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching metrics: {str(e)}"
        )

def generate_monthly_data():
    """Generate monthly data for the last 6 months"""
    monthly_data = []
    current_date = datetime.now()
    
    # Generate data for last 6 months
    for i in range(5, -1, -1):
        month_date = current_date - timedelta(days=30*i)
        month_name = month_date.strftime("%b")
        
        # Calculate start and end of the month
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(seconds=1)
        
        # Get users created in this month
        users_result = supabase.table("users").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get products created in this month
        products_result = supabase.table("products").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get orders created in this month
        orders_result = supabase.table("orders").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        # Get shops created in this month
        shops_result = supabase.table("shops").select("id", count="exact").gte(
            "created_at", month_start.isoformat()
        ).lte(
            "created_at", month_end.isoformat()
        ).execute()
        
        monthly_data.append({
            "name": month_name,
            "users": users_result.count or 0,
            "products": products_result.count or 0,
            "orders": orders_result.count or 0,
            "shops": shops_result.count or 0
        })
    
    return monthly_data

def calculate_growth(monthly_data, metric):
    """Calculate growth percentage for the last month compared to previous month"""
    if len(monthly_data) < 2:
        return 0
    
    current_month = monthly_data[-1].get(metric, 0)
    previous_month = monthly_data[-2].get(metric, 0)
    
    if previous_month == 0:
        return 100 if current_month > 0 else 0
    
    growth = ((current_month - previous_month) / previous_month) * 100
    return round(growth, 1)