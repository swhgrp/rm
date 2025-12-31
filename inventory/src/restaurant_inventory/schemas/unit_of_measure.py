from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime


# Unit Category Schemas
class UnitCategoryBase(BaseModel):
    name: str = Field(..., max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class UnitCategoryCreate(UnitCategoryBase):
    pass


class UnitCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class UnitCategoryResponse(UnitCategoryBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Unit of Measure Schemas
class UnitOfMeasureBase(BaseModel):
    category_id: int
    name: str = Field(..., max_length=50)
    abbreviation: str = Field(..., max_length=50)
    reference_unit_id: Optional[int] = Field(None, description="The unit this one references")
    contains_quantity: Optional[Decimal] = Field(None, description="How many reference units this contains")
    is_active: bool = True


class UnitOfMeasureCreate(UnitOfMeasureBase):
    pass


class UnitOfMeasureUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=50)
    abbreviation: Optional[str] = Field(None, max_length=50)
    reference_unit_id: Optional[int] = None
    contains_quantity: Optional[Decimal] = None
    is_active: Optional[bool] = None


class UnitOfMeasureResponse(UnitOfMeasureBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    category_name: Optional[str] = None  # Populated from join
    reference_unit_name: Optional[str] = None  # Populated from join
    dimension: Optional[str] = None  # count, volume, weight, length

    @field_serializer('contains_quantity')
    def serialize_contains_quantity(self, value: Optional[Decimal]) -> Optional[float]:
        """Round contains quantity to 3 decimal places for display"""
        if value is None:
            return None
        return float(value.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP))

    class Config:
        from_attributes = True


# Unit Category with Units
class UnitCategoryWithUnits(UnitCategoryResponse):
    units: List[UnitOfMeasureResponse] = []

    class Config:
        from_attributes = True


# Conversion Request/Response
class UnitConversionRequest(BaseModel):
    from_unit_id: int
    to_unit_id: int
    quantity: Decimal


class UnitConversionResponse(BaseModel):
    from_unit: str
    to_unit: str
    input_quantity: Decimal
    converted_quantity: Decimal
    conversion_factor: Decimal

    @field_serializer('converted_quantity', 'input_quantity', 'conversion_factor')
    def serialize_decimal_fields(self, value: Decimal) -> float:
        """Round quantities to 3 decimal places for display"""
        return float(value.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP))
