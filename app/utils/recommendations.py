from app.database import supabase
from datetime import datetime, timedelta

class RecommendationEngine:
    def __init__(self):
        self.weights = {
            'popularity': 0.4,
            'recency': 0.3,
            'shop_rating': 0.3
        }
    
    def get_popular_products(self, limit: int = 20):
        """Get popular products based on views and orders"""
        # Simple popularity based on recent orders
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Get products with recent orders
        result = supabase.table('order_items') \
            .select('product_id, count') \
            .gte('created_at', week_ago) \
            .execute()
        
        # This is a simplified version - in production, you'd use more sophisticated scoring
        popular_products = [item['product_id'] for item in result.data]
        return popular_products[:limit]
    
    def get_personalized_recommendations(self, user_id: str, limit: int = 10):
        """Get personalized recommendations for a user"""
        # For MVP, return popular products
        # In phase 2, implement collaborative filtering
        return self.get_popular_products(limit)

recommendation_engine = RecommendationEngine()