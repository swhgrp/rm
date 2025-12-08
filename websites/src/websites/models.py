"""
Database models for the Website Management System
"""
from datetime import datetime, time, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, Time,
    ForeignKey, DECIMAL, ARRAY, UniqueConstraint, Index, Numeric
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Site(Base):
    """Restaurant website configuration"""
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)  # "Seaside Grill"
    slug = Column(String(100), unique=True, nullable=False)  # "seaside-grill"
    domain = Column(String(255))  # "seasidegrillvero.com"

    # Branding
    logo_url = Column(String(500))
    favicon_url = Column(String(500))
    primary_color = Column(String(7), default="#1a1a1a")
    secondary_color = Column(String(7), default="#ffffff")
    accent_color = Column(String(7), default="#c9a227")
    font_heading = Column(String(100), default="Playfair Display")
    font_body = Column(String(100), default="Open Sans")

    # Contact info
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    phone = Column(String(20))
    email = Column(String(255))

    # Social media
    instagram_url = Column(String(255))
    facebook_url = Column(String(255))

    # External links
    online_ordering_url = Column(String(500))  # Clover link
    reservation_url = Column(String(500))

    # SEO
    seo_title = Column(String(255))
    seo_description = Column(Text)
    google_analytics_id = Column(String(50))

    # State
    is_published = Column(Boolean, default=False)
    last_generated_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    menus = relationship("Menu", back_populates="site", cascade="all, delete-orphan")
    hours = relationship("Hours", back_populates="site", cascade="all, delete-orphan")
    special_hours = relationship("SpecialHours", back_populates="site", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="site", cascade="all, delete-orphan")
    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")
    form_submissions = relationship("FormSubmission", back_populates="site", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="site", cascade="all, delete-orphan")


class Menu(Base):
    """Restaurant menu (Breakfast, Lunch, Dinner, etc.)"""
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # "Dinner Menu"
    slug = Column(String(100), nullable=False)  # "dinner"
    description = Column(Text)
    served_days = Column(ARRAY(Integer))  # [1,2,3,4,5] for Mon-Fri
    served_start_time = Column(Time)
    served_end_time = Column(Time)
    footer_note = Column(Text)  # "Consuming raw or undercooked..."
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("site_id", "slug", name="uq_menu_site_slug"),
        Index("idx_menus_site", "site_id"),
    )

    # Relationships
    site = relationship("Site", back_populates="menus")
    categories = relationship("MenuCategory", back_populates="menu",
                             cascade="all, delete-orphan", order_by="MenuCategory.sort_order")


class MenuCategory(Base):
    """Category within a menu (The Classics, Omelettes, etc.)"""
    __tablename__ = "menu_categories"

    id = Column(Integer, primary_key=True)
    menu_id = Column(Integer, ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_categories_menu", "menu_id"),
    )

    # Relationships
    menu = relationship("Menu", back_populates="categories")
    items = relationship("MenuItem", back_populates="category",
                        cascade="all, delete-orphan", order_by="MenuItem.sort_order")


class MenuItem(Base):
    """Individual menu item"""
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2))
    price_label = Column(String(50))  # "Market Price", "Small/Large"
    price_variants = Column(JSONB)  # [{"label": "Small", "price": 12.00}, ...]
    image_url = Column(String(500))
    dietary_flags = Column(ARRAY(String(50)))  # ['vegetarian', 'gluten-free', 'spicy']
    is_featured = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_items_category", "category_id"),
    )

    # Relationships
    category = relationship("MenuCategory", back_populates="items")


class Hours(Base):
    """Regular operating hours"""
    __tablename__ = "hours"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Sunday, 6=Saturday
    open_time = Column(Time)
    close_time = Column(Time)
    is_closed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("site_id", "day_of_week", name="uq_hours_site_day"),
    )

    # Relationships
    site = relationship("Site", back_populates="hours")


class SpecialHours(Base):
    """Special hours for holidays, events, etc."""
    __tablename__ = "special_hours"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    label = Column(String(100))  # "Thanksgiving"
    open_time = Column(Time)
    close_time = Column(Time)
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    site = relationship("Site", back_populates="special_hours")


class Image(Base):
    """Uploaded images"""
    __tablename__ = "images"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    folder = Column(String(100), default="general")  # "menu", "gallery", "hero"
    alt_text = Column(String(255))
    mime_type = Column(String(50))
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    # Generated variants
    thumb_url = Column(String(500))  # 150px
    medium_url = Column(String(500))  # 600px
    large_url = Column(String(500))  # 1200px
    webp_url = Column(String(500))  # WebP version
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_images_site", "site_id"),
    )

    # Relationships
    site = relationship("Site", back_populates="images")


class Page(Base):
    """Website pages"""
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False)  # "about", "contact"
    template = Column(String(50), default="page")  # "page", "menu", "home"
    seo_title = Column(String(255))
    seo_description = Column(Text)
    is_published = Column(Boolean, default=False)
    is_in_nav = Column(Boolean, default=True)
    nav_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("site_id", "slug", name="uq_page_site_slug"),
        Index("idx_pages_site", "site_id"),
    )

    # Relationships
    site = relationship("Site", back_populates="pages")
    blocks = relationship("PageBlock", back_populates="page",
                         cascade="all, delete-orphan", order_by="PageBlock.sort_order")


class PageBlock(Base):
    """Content blocks within pages"""
    __tablename__ = "page_blocks"

    id = Column(Integer, primary_key=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    block_type = Column(String(50), nullable=False)  # 'hero', 'text', 'gallery', etc.
    content = Column(JSONB, nullable=False, default={})
    sort_order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_blocks_page", "page_id"),
    )

    # Relationships
    page = relationship("Page", back_populates="blocks")


class FormSubmission(Base):
    """Contact form submissions"""
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    page_slug = Column(String(100))
    name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    subject = Column(String(255))
    message = Column(Text)
    ip_address = Column(INET)
    is_read = Column(Boolean, default=False)
    is_spam = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_submissions_site", "site_id", "created_at"),
    )

    # Relationships
    site = relationship("Site", back_populates="form_submissions")


class ActivityLog(Base):
    """Audit log for changes"""
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"))
    user_id = Column(Integer)  # From portal
    user_name = Column(String(100))
    action = Column(String(50))  # 'create', 'update', 'delete', 'publish'
    entity_type = Column(String(50))  # 'menu', 'page', 'site'
    entity_id = Column(Integer)
    entity_name = Column(String(255))
    details = Column(JSONB)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_activity_site", "site_id", "created_at"),
    )

    # Relationships
    site = relationship("Site", back_populates="activity_logs")
