"""
Pydantic schemas for request/response validation
"""
from datetime import datetime, time, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from decimal import Decimal


# ============ Site Schemas ============

class SiteBase(BaseModel):
    name: str
    slug: str
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#1a1a1a"
    secondary_color: str = "#ffffff"
    accent_color: str = "#c9a227"
    font_heading: str = "Playfair Display"
    font_body: str = "Open Sans"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    online_ordering_url: Optional[str] = None
    reservation_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    google_analytics_id: Optional[str] = None


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_heading: Optional[str] = None
    font_body: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    online_ordering_url: Optional[str] = None
    reservation_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    google_analytics_id: Optional[str] = None


class SiteResponse(SiteBase):
    id: int
    is_published: bool
    last_generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Menu Schemas ============

class MenuItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[Decimal] = None
    price_label: Optional[str] = None
    price_variants: Optional[List[dict]] = None
    image_url: Optional[str] = None
    dietary_flags: Optional[List[str]] = None
    is_featured: bool = False
    is_available: bool = True
    sort_order: int = 0


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    price_label: Optional[str] = None
    price_variants: Optional[List[dict]] = None
    image_url: Optional[str] = None
    dietary_flags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    is_available: Optional[bool] = None
    sort_order: Optional[int] = None


class MenuItemResponse(MenuItemBase):
    id: int
    category_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class MenuCategoryCreate(MenuCategoryBase):
    pass


class MenuCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class MenuCategoryResponse(MenuCategoryBase):
    id: int
    menu_id: int
    items: List[MenuItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    served_days: Optional[List[int]] = None
    served_start_time: Optional[time] = None
    served_end_time: Optional[time] = None
    footer_note: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class MenuCreate(MenuBase):
    pass


class MenuUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    served_days: Optional[List[int]] = None
    served_start_time: Optional[time] = None
    served_end_time: Optional[time] = None
    footer_note: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MenuResponse(MenuBase):
    id: int
    site_id: int
    categories: List[MenuCategoryResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuListResponse(BaseModel):
    id: int
    site_id: int
    name: str
    slug: str
    is_active: bool
    sort_order: int
    category_count: int = 0
    item_count: int = 0

    class Config:
        from_attributes = True


# ============ Hours Schemas ============

class HoursBase(BaseModel):
    day_of_week: int  # 0=Sunday, 6=Saturday
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    is_closed: bool = False


class HoursUpdate(BaseModel):
    hours: List[HoursBase]


class HoursResponse(HoursBase):
    id: int
    site_id: int

    class Config:
        from_attributes = True


class SpecialHoursBase(BaseModel):
    date: date
    label: Optional[str] = None
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    is_closed: bool = False


class SpecialHoursCreate(SpecialHoursBase):
    pass


class SpecialHoursResponse(SpecialHoursBase):
    id: int
    site_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Image Schemas ============

class ImageResponse(BaseModel):
    id: int
    site_id: int
    filename: str
    original_filename: Optional[str] = None
    folder: str
    alt_text: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    thumb_url: Optional[str] = None
    medium_url: Optional[str] = None
    large_url: Optional[str] = None
    webp_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ImageUpdate(BaseModel):
    alt_text: Optional[str] = None
    folder: Optional[str] = None


# ============ Page Schemas ============

class PageBlockBase(BaseModel):
    block_type: str
    content: dict = {}
    sort_order: int = 0
    is_visible: bool = True


class PageBlockCreate(PageBlockBase):
    pass


class PageBlockUpdate(BaseModel):
    block_type: Optional[str] = None
    content: Optional[dict] = None
    sort_order: Optional[int] = None
    is_visible: Optional[bool] = None


class PageBlockResponse(PageBlockBase):
    id: int
    page_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PageBase(BaseModel):
    title: str
    slug: str
    template: str = "page"
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    is_published: bool = False
    is_in_nav: bool = True
    nav_order: int = 0


class PageCreate(PageBase):
    pass


class PageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    template: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    is_published: Optional[bool] = None
    is_in_nav: Optional[bool] = None
    nav_order: Optional[int] = None


class PageResponse(PageBase):
    id: int
    site_id: int
    blocks: List[PageBlockResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PageListResponse(BaseModel):
    id: int
    site_id: int
    title: str
    slug: str
    template: str
    is_published: bool
    is_in_nav: bool
    nav_order: int
    block_count: int = 0

    class Config:
        from_attributes = True


# ============ Form Submission Schemas ============

class FormSubmissionCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None


class FormSubmissionResponse(BaseModel):
    id: int
    site_id: int
    page_slug: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    is_read: bool
    is_spam: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Activity Log Schemas ============

class ActivityLogResponse(BaseModel):
    id: int
    site_id: Optional[int] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    entity_name: Optional[str] = None
    details: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Reorder Schemas ============

class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]
