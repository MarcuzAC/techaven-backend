from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# Import routers
from app.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.shops import router as shops_router
from app.routes.products import router as products_router
from app.routes.orders import router as orders_router
from app.routes.promotions import router as promotions_router
from app.routes.admin import router as admin_router

app = FastAPI(
    title="Techaven API",
    description="Electronics Marketplace Backend",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://techaven-admin.vercel.app", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(shops_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(promotions_router)
app.include_router(admin_router)

@app.get("/")
async def root():
    return {"message": "Tech Havan API is running 🚀"}

@app.get("/health")
async def health_check():
    from app.database import test_connection
    db_status = test_connection()
    return {
        "status": "healthy",
        "database": "connected" if db_status else "disconnected"
    }

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)