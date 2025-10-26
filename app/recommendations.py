from app.database import supabase
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

# Blockchain imports
from app.blockchain.service import blockchain_service
from app.blockchain.models import TransactionType

class RecommendationEngine:
    def __init__(self):
        self.weights = {
            'popularity': 0.25,
            'recency': 0.2,
            'shop_rating': 0.15,
            'blockchain_activity': 0.2,
            'user_similarity': 0.2
        }
    
    def get_popular_products(self, limit: int = 20):
        """Get popular products based on views, orders, and blockchain activity"""
        # Get products with recent orders (last 30 days)
        month_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        # Get products from recent orders
        order_items_result = supabase.table('order_items') \
            .select('product_id, products(*)') \
            .gte('created_at', month_ago) \
            .execute()
        
        # Count orders per product
        product_orders = {}
        for item in order_items_result.data:
            product_id = item['product_id']
            product_orders[product_id] = product_orders.get(product_id, 0) + 1
        
        # Get blockchain activity for products
        product_scores = self._calculate_blockchain_product_scores()
        
        # Combine scores
        popular_products = []
        for product_id, order_count in product_orders.items():
            blockchain_score = product_scores.get(product_id, 0)
            total_score = (order_count * 0.7) + (blockchain_score * 0.3)
            
            # Get product details
            product_details = next((item['products'] for item in order_items_result.data 
                                  if item['product_id'] == product_id), None)
            
            if product_details:
                popular_products.append({
                    **product_details,
                    'score': total_score,
                    'order_count': order_count,
                    'blockchain_score': blockchain_score
                })
        
        # Sort by score and return
        popular_products.sort(key=lambda x: x['score'], reverse=True)
        return popular_products[:limit]
    
    def get_personalized_recommendations(self, user_id: str, limit: int = 10):
        """Get personalized recommendations using blockchain data and user behavior"""
        try:
            # Get user's blockchain activity
            user_transactions = blockchain_service.get_transactions_by_user(user_id)
            
            # Get user's order history
            user_orders = supabase.table('orders') \
                .select('*, order_items(*, products(*))') \
                .eq('user_id', user_id) \
                .execute()
            
            # Phase 1: Content-based filtering using purchased categories
            content_based_recs = self._get_content_based_recommendations(user_orders.data, limit)
            
            # Phase 2: Blockchain-powered collaborative filtering
            blockchain_recs = self._get_blockchain_based_recommendations(user_id, user_transactions, limit)
            
            # Phase 3: Popular products as fallback
            popular_recs = self.get_popular_products(limit)
            
            # Combine and deduplicate recommendations
            all_recommendations = self._combine_recommendations(
                content_based_recs, blockchain_recs, popular_recs, limit
            )
            
            return {
                "recommendations": all_recommendations,
                "recommendation_breakdown": {
                    "content_based": len(content_based_recs),
                    "blockchain_based": len(blockchain_recs),
                    "popular": len(popular_recs)
                },
                "user_activity_insights": self._get_user_activity_insights(user_transactions, user_orders.data)
            }
            
        except Exception as e:
            print(f"Error generating personalized recommendations: {e}")
            # Fallback to popular products
            return {
                "recommendations": self.get_popular_products(limit),
                "recommendation_breakdown": {"fallback": limit},
                "user_activity_insights": {}
            }
    
    def get_shop_recommendations(self, shop_id: str, limit: int = 5):
        """Get recommendations for shop improvement based on blockchain data"""
        try:
            # Get shop's blockchain transactions
            shop_transactions = blockchain_service.get_transactions_by_shop(shop_id)
            
            # Get shop's products and their performance
            shop_products = supabase.table('products') \
                .select('*, order_items(*)') \
                .eq('shop_id', shop_id) \
                .execute()
            
            insights = {
                "performance_metrics": self._calculate_shop_performance(shop_transactions, shop_products.data),
                "improvement_suggestions": self._generate_shop_improvement_suggestions(shop_transactions),
                "competitive_analysis": self._get_competitive_analysis(shop_id)
            }
            
            return insights
            
        except Exception as e:
            print(f"Error generating shop recommendations: {e}")
            return {}
    
    def get_trending_products(self, days: int = 7, limit: int = 15):
        """Get trending products based on recent blockchain activity"""
        try:
            # Get recent blockchain transactions
            recent_transactions = []
            time_threshold = datetime.now() - timedelta(days=days)
            
            for block in blockchain_service.blockchain.chain:
                if block.timestamp >= time_threshold:
                    for tx in block.transactions:
                        if tx.transaction_type in [TransactionType.ORDER_CREATE, TransactionType.PRODUCT_CREATE]:
                            recent_transactions.append(tx)
            
            # Analyze product trends
            product_trends = {}
            for tx in recent_transactions:
                if tx.product_id:
                    product_id = tx.product_id
                    if product_id not in product_trends:
                        product_trends[product_id] = {
                            'order_count': 0,
                            'creation_time': tx.timestamp,
                            'recent_activity': 0
                        }
                    
                    if tx.transaction_type == TransactionType.ORDER_CREATE:
                        product_trends[product_id]['order_count'] += 1
                    product_trends[product_id]['recent_activity'] += 1
            
            # Get product details and calculate trend scores
            trending_products = []
            for product_id, trends in product_trends.items():
                product_result = supabase.table('products') \
                    .select('*, shops(name, rating)') \
                    .eq('id', product_id) \
                    .execute()
                
                if product_result.data:
                    product = product_result.data[0]
                    
                    # Calculate trend score
                    trend_score = (
                        trends['order_count'] * 0.5 +
                        trends['recent_activity'] * 0.3 +
                        (product['shops']['rating'] or 0) * 0.2
                    )
                    
                    trending_products.append({
                        **product,
                        'trend_score': trend_score,
                        'recent_orders': trends['order_count'],
                        'activity_count': trends['recent_activity']
                    })
            
            trending_products.sort(key=lambda x: x['trend_score'], reverse=True)
            return trending_products[:limit]
            
        except Exception as e:
            print(f"Error getting trending products: {e}")
            return self.get_popular_products(limit)
    
    def _calculate_blockchain_product_scores(self) -> Dict[str, float]:
        """Calculate product scores based on blockchain activity"""
        product_scores = {}
        
        for block in blockchain_service.blockchain.chain:
            for tx in block.transactions:
                if tx.product_id:
                    product_id = tx.product_id
                    
                    if product_id not in product_scores:
                        product_scores[product_id] = 0
                    
                    # Different transaction types contribute differently to score
                    score_weights = {
                        TransactionType.ORDER_CREATE: 2.0,
                        TransactionType.PRODUCT_CREATE: 1.0,
                        TransactionType.PRODUCT_UPDATE: 0.5,
                        TransactionType.PRICE_UPDATE: 0.3,
                        TransactionType.REVIEW_CREATE: 1.5
                    }
                    
                    product_scores[product_id] += score_weights.get(tx.transaction_type, 0.1)
        
        return product_scores
    
    def _get_content_based_recommendations(self, user_orders: List, limit: int) -> List[Dict]:
        """Content-based filtering using user's purchase history"""
        if not user_orders:
            return []
        
        # Extract categories/brands from purchased products
        purchased_categories = set()
        purchased_brands = set()
        
        for order in user_orders:
            for item in order.get('order_items', []):
                product = item.get('products', {})
                purchased_brands.add(product.get('brand', ''))
                # You could add category here if you have categories in your product model
        
        # Find similar products
        similar_products = []
        if purchased_brands:
            brand_list = list(purchased_brands)[:3]  # Top 3 brands
            for brand in brand_list:
                brand_products = supabase.table('products') \
                    .select('*, shops(name, rating)') \
                    .eq('brand', brand) \
                    .limit(5) \
                    .execute()
                
                similar_products.extend(brand_products.data)
        
        # Remove duplicates and products user already purchased
        purchased_product_ids = set()
        for order in user_orders:
            for item in order.get('order_items', []):
                purchased_product_ids.add(item.get('product_id'))
        
        filtered_recs = [
            product for product in similar_products 
            if product.get('id') not in purchased_product_ids
        ]
        
        return filtered_recs[:limit]
    
    def _get_blockchain_based_recommendations(self, user_id: str, user_transactions: List, limit: int) -> List[Dict]:
        """Blockchain-powered collaborative filtering"""
        # Find users with similar blockchain activity patterns
        similar_users = self._find_similar_users(user_id, user_transactions)
        
        if not similar_users:
            return []
        
        # Get products that similar users have purchased
        similar_products = set()
        for similar_user_id in similar_users[:5]:  # Top 5 similar users
            user_orders = supabase.table('orders') \
                .select('order_items(product_id)') \
                .eq('user_id', similar_user_id) \
                .execute()
            
            for order in user_orders.data:
                for item in order.get('order_items', []):
                    similar_products.add(item.get('product_id'))
        
        # Get product details
        recommendations = []
        for product_id in list(similar_products)[:limit]:
            product_result = supabase.table('products') \
                .select('*, shops(name, rating)') \
                .eq('id', product_id) \
                .execute()
            
            if product_result.data:
                recommendations.append(product_result.data[0])
        
        return recommendations
    
    def _find_similar_users(self, user_id: str, user_transactions: List) -> List[str]:
        """Find users with similar blockchain activity patterns"""
        # This is a simplified version - in production, use more sophisticated algorithms
        
        user_activity_pattern = {}
        for tx in user_transactions:
            activity_type = f"{tx.transaction_type.value}_{tx.shop_id or 'global'}"
            user_activity_pattern[activity_type] = user_activity_pattern.get(activity_type, 0) + 1
        
        # For MVP, return some random users
        # In production, implement proper similarity calculation
        similar_users_result = supabase.table('users') \
            .select('id') \
            .neq('id', user_id) \
            .limit(10) \
            .execute()
        
        return [user['id'] for user in similar_users_result.data]
    
    def _combine_recommendations(self, *recommendation_lists, limit: int) -> List[Dict]:
        """Combine multiple recommendation lists with deduplication"""
        all_recommendations = []
        seen_products = set()
        
        for rec_list in recommendation_lists:
            for product in rec_list:
                product_id = product.get('id')
                if product_id and product_id not in seen_products:
                    seen_products.add(product_id)
                    all_recommendations.append(product)
                
                if len(all_recommendations) >= limit:
                    break
            
            if len(all_recommendations) >= limit:
                break
        
        return all_recommendations[:limit]
    
    def _get_user_activity_insights(self, user_transactions: List, user_orders: List) -> Dict[str, Any]:
        """Generate insights from user's blockchain activity"""
        if not user_transactions:
            return {}
        
        # Analyze transaction types
        transaction_counts = {}
        for tx in user_transactions:
            tx_type = tx.transaction_type.value
            transaction_counts[tx_type] = transaction_counts.get(tx_type, 0) + 1
        
        # Calculate activity metrics
        total_orders = len(user_orders)
        favorite_shops = self._get_favorite_shops(user_transactions)
        
        return {
            "total_blockchain_activities": len(user_transactions),
            "transaction_breakdown": transaction_counts,
            "purchase_history": {
                "total_orders": total_orders,
                "first_order_date": min([order['created_at'] for order in user_orders]) if user_orders else None
            },
            "preferences": {
                "favorite_shops": favorite_shops[:3],
                "active_categories": self._get_active_categories(user_transactions)
            }
        }
    
    def _get_favorite_shops(self, user_transactions: List) -> List[Dict]:
        """Get user's favorite shops based on blockchain activity"""
        shop_activity = {}
        
        for tx in user_transactions:
            if tx.shop_id:
                shop_activity[tx.shop_id] = shop_activity.get(tx.shop_id, 0) + 1
        
        # Get shop details
        favorite_shops = []
        for shop_id, activity_count in sorted(shop_activity.items(), key=lambda x: x[1], reverse=True)[:5]:
            shop_result = supabase.table('shops') \
                .select('id, name, rating') \
                .eq('id', shop_id) \
                .execute()
            
            if shop_result.data:
                favorite_shops.append({
                    **shop_result.data[0],
                    'user_activity_count': activity_count
                })
        
        return favorite_shops
    
    def _get_active_categories(self, user_transactions: List) -> List[str]:
        """Extract active categories from user's blockchain activity"""
        # This would require a category field in your product model
        # For now, return empty list
        return []
    
    def _calculate_shop_performance(self, shop_transactions: List, shop_products: List) -> Dict[str, Any]:
        """Calculate shop performance metrics from blockchain data"""
        performance = {
            "total_transactions": len(shop_transactions),
            "order_volume": 0,
            "product_updates": 0,
            "customer_engagement": 0
        }
        
        for tx in shop_transactions:
            if tx.transaction_type == TransactionType.ORDER_CREATE:
                performance["order_volume"] += 1
            elif tx.transaction_type == TransactionType.PRODUCT_UPDATE:
                performance["product_updates"] += 1
            elif tx.transaction_type in [TransactionType.PRICE_UPDATE, TransactionType.STOCK_UPDATE]:
                performance["customer_engagement"] += 1
        
        return performance
    
    def _generate_shop_improvement_suggestions(self, shop_transactions: List) -> List[str]:
        """Generate improvement suggestions for shops based on blockchain data"""
        suggestions = []
        
        # Analyze transaction patterns
        order_count = len([tx for tx in shop_transactions if tx.transaction_type == TransactionType.ORDER_CREATE])
        update_count = len([tx for tx in shop_transactions if tx.transaction_type == TransactionType.PRODUCT_UPDATE])
        
        if order_count < 10:
            suggestions.append("Consider adding more products to attract customers")
        
        if update_count < 5:
            suggestions.append("Regularly update product information to maintain customer trust")
        
        return suggestions
    
    def _get_competitive_analysis(self, shop_id: str) -> Dict[str, Any]:
        """Get competitive analysis for a shop"""
        # Simplified competitive analysis
        # In production, implement more sophisticated analysis
        
        # Get similar shops
        similar_shops = supabase.table('shops') \
            .select('id, name, rating, verified') \
            .neq('id', shop_id) \
            .limit(5) \
            .execute()
        
        return {
            "similar_shops": similar_shops.data,
            "market_position": "growing"  # Simplified position
        }

# Global recommendation engine instance
recommendation_engine = RecommendationEngine()