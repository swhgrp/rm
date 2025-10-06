#!/usr/bin/env python3
"""
Create all database tables from SQLAlchemy models
"""
import sys
sys.path.insert(0, '/app/src')

from restaurant_inventory.db.database import Base, engine

# Import all models to register them with Base
from restaurant_inventory.models.user import User
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.storage_area import StorageArea
from restaurant_inventory.models.category import Category
from restaurant_inventory.models.vendor import Vendor
from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.vendor_item import VendorItem
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.transfer import Transfer
from restaurant_inventory.models.waste import WasteRecord
from restaurant_inventory.models.count_template import CountTemplate, CountTemplateItem
from restaurant_inventory.models.count_session import CountSession, CountSessionItem
from restaurant_inventory.models.invoice import Invoice, InvoiceItem
from restaurant_inventory.models.recipe import Recipe, RecipeIngredient
from restaurant_inventory.models.pos_sale import POSSale
from restaurant_inventory.models.audit_log import AuditLog
from restaurant_inventory.models.role import Role

print("Creating all database tables...")
Base.metadata.create_all(bind=engine)
print("Done! All tables created successfully.")
