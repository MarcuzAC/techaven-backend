from supabase import create_client
from app.config import settings

# Supabase client
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Test connection
def test_connection():
    try:
        result = supabase.table('users').select('*').limit(1).execute()
        print("✅ Supabase connection successful")
        return True
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return False