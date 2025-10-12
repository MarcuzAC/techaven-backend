import uuid
from app.database import supabase
from app.config import settings

async def upload_product_image(file_content: bytes, filename: str) -> str:
    """Upload product image to Supabase storage"""
    file_extension = filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    
    try:
        result = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            unique_filename, file_content
        )
        return unique_filename
    except Exception as e:
        raise Exception(f"Failed to upload image: {str(e)}")

def get_image_url(filename: str) -> str:
    """Get public URL for stored image"""
    try:
        response = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).get_public_url(filename)
        return response
    except Exception as e:
        raise Exception(f"Failed to get image URL: {str(e)}")