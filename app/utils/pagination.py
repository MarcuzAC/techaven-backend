from typing import Any, List, Tuple
from sqlalchemy.orm import Query
from math import ceil

def apply_pagination(query: Query, offset: int, limit: int) -> Query:
    """Apply pagination to SQLAlchemy query."""
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = 20
    if limit > 100:  # Max limit
        limit = 100
    
    return query.offset(offset).limit(limit)

def get_pagination_info(
    total: int, 
    offset: int, 
    limit: int
) -> dict:
    """Get pagination metadata."""
    if limit <= 0:
        limit = 20
    
    page = (offset // limit) + 1 if limit > 0 else 1
    pages = ceil(total / limit) if limit > 0 else 1
    has_next = offset + limit < total
    has_previous = offset > 0
    
    return {
        "total": total,
        "page": page,
        "size": limit,
        "pages": pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_offset": offset + limit if has_next else None,
        "prev_offset": offset - limit if has_previous else None
    }

def paginate_list(
    items: List[Any], 
    offset: int, 
    limit: int
) -> Tuple[List[Any], dict]:
    """Paginate a list of items."""
    total = len(items)
    
    # Apply pagination
    start = offset
    end = offset + limit
    paginated_items = items[start:end]
    
    # Get pagination info
    pagination_info = get_pagination_info(total, offset, limit)
    
    return paginated_items, pagination_info

def validate_pagination_params(offset: int, limit: int) -> Tuple[int, int]:
    """Validate and normalize pagination parameters."""
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100
    
    return offset, limit

def get_page_links(
    base_url: str,
    current_page: int,
    total_pages: int,
    page_size: int
) -> dict:
    """Get pagination links for API responses."""
    links = {
        "first": f"{base_url}?page=1&size={page_size}",
        "last": f"{base_url}?page={total_pages}&size={page_size}" if total_pages > 0 else f"{base_url}?page=1&size={page_size}",
        "self": f"{base_url}?page={current_page}&size={page_size}"
    }
    
    if current_page > 1:
        links["prev"] = f"{base_url}?page={current_page - 1}&size={page_size}"
    
    if current_page < total_pages:
        links["next"] = f"{base_url}?page={current_page + 1}&size={page_size}"
    
    return links