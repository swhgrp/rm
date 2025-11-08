"""Settings API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from uuid import UUID

from events.core.database import get_db
from events.core.deps import require_auth, require_role
from events.models import Location, EventType, BeverageService, MealType, EventTemplate, User
from events.schemas.settings import (
    LocationCreate, LocationUpdate, LocationResponse,
    EventTypeCreate, EventTypeUpdate, EventTypeResponse,
    BeverageServiceCreate, BeverageServiceUpdate, BeverageServiceResponse,
    MealTypeCreate, MealTypeUpdate, MealTypeResponse
)
from events.schemas.template import (
    EventTemplateCreate, EventTemplateUpdate, EventTemplateResponse
)

router = APIRouter()


# ============= LOCATIONS =============

@router.get("/locations", response_model=List[LocationResponse])
async def list_locations(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all locations"""
    query = db.query(Location)
    if not include_inactive:
        query = query.filter(Location.is_active == True)
    locations = query.order_by(Location.sort_order.asc(), Location.name.asc()).all()
    return locations


@router.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get location by ID"""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.post("/locations", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    location_data: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create new location"""
    location = Location(**location_data.dict())
    try:
        db.add(location)
        db.commit()
        db.refresh(location)
        return location
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Location with this name already exists")


@router.patch("/locations/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: UUID,
    location_data: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update location"""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    update_dict = location_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(location, field, value)
    
    try:
        db.commit()
        db.refresh(location)
        return location
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Location with this name already exists")


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete location"""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    db.delete(location)
    db.commit()
    return None


# ============= EVENT TYPES =============

@router.get("/event-types", response_model=List[EventTypeResponse])
async def list_event_types(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all event types"""
    query = db.query(EventType)
    if not include_inactive:
        query = query.filter(EventType.is_active == True)
    event_types = query.order_by(EventType.sort_order.asc(), EventType.name.asc()).all()
    return event_types


@router.get("/event-types/{event_type_id}", response_model=EventTypeResponse)
async def get_event_type(
    event_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get event type by ID"""
    event_type = db.query(EventType).filter(EventType.id == event_type_id).first()
    if not event_type:
        raise HTTPException(status_code=404, detail="Event type not found")
    return event_type


@router.post("/event-types", response_model=EventTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_event_type(
    event_type_data: EventTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create new event type"""
    event_type = EventType(**event_type_data.dict())
    try:
        db.add(event_type)
        db.commit()
        db.refresh(event_type)
        return event_type
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Event type with this name already exists")


@router.patch("/event-types/{event_type_id}", response_model=EventTypeResponse)
async def update_event_type(
    event_type_id: UUID,
    event_type_data: EventTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update event type"""
    event_type = db.query(EventType).filter(EventType.id == event_type_id).first()
    if not event_type:
        raise HTTPException(status_code=404, detail="Event type not found")

    update_dict = event_type_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(event_type, field, value)

    try:
        db.commit()
        db.refresh(event_type)
        return event_type
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Event type with this name already exists")


@router.delete("/event-types/{event_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_type(
    event_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete event type"""
    event_type = db.query(EventType).filter(EventType.id == event_type_id).first()
    if not event_type:
        raise HTTPException(status_code=404, detail="Event type not found")
    
    db.delete(event_type)
    db.commit()
    return None


# ============= BEVERAGE SERVICES =============

@router.get("/beverage-services", response_model=List[BeverageServiceResponse])
async def list_beverage_services(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all beverage services"""
    query = db.query(BeverageService)
    if not include_inactive:
        query = query.filter(BeverageService.is_active == True)
    services = query.order_by(BeverageService.sort_order.asc(), BeverageService.name.asc()).all()
    return services


@router.get("/beverage-services/{service_id}", response_model=BeverageServiceResponse)
async def get_beverage_service(
    service_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get beverage service by ID"""
    service = db.query(BeverageService).filter(BeverageService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Beverage service not found")
    return service


@router.post("/beverage-services", response_model=BeverageServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_beverage_service(
    service_data: BeverageServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create new beverage service"""
    service = BeverageService(**service_data.dict())
    try:
        db.add(service)
        db.commit()
        db.refresh(service)
        return service
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Beverage service with this name already exists")


@router.patch("/beverage-services/{service_id}", response_model=BeverageServiceResponse)
async def update_beverage_service(
    service_id: UUID,
    service_data: BeverageServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update beverage service"""
    service = db.query(BeverageService).filter(BeverageService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Beverage service not found")

    update_dict = service_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(service, field, value)

    try:
        db.commit()
        db.refresh(service)
        return service
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Beverage service with this name already exists")


@router.delete("/beverage-services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_beverage_service(
    service_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete beverage service"""
    service = db.query(BeverageService).filter(BeverageService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Beverage service not found")
    
    db.delete(service)
    db.commit()
    return None


# ============= MEAL TYPES =============

@router.get("/meal-types", response_model=List[MealTypeResponse])
async def list_meal_types(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all meal types"""
    query = db.query(MealType)
    if not include_inactive:
        query = query.filter(MealType.is_active == True)
    meal_types = query.order_by(MealType.sort_order.asc(), MealType.name.asc()).all()
    return meal_types


@router.get("/meal-types/{meal_type_id}", response_model=MealTypeResponse)
async def get_meal_type(
    meal_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get meal type by ID"""
    meal_type = db.query(MealType).filter(MealType.id == meal_type_id).first()
    if not meal_type:
        raise HTTPException(status_code=404, detail="Meal type not found")
    return meal_type


@router.post("/meal-types", response_model=MealTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_meal_type(
    meal_type_data: MealTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create new meal type"""
    meal_type = MealType(**meal_type_data.dict())
    try:
        db.add(meal_type)
        db.commit()
        db.refresh(meal_type)
        return meal_type
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Meal type with this name already exists")


@router.patch("/meal-types/{meal_type_id}", response_model=MealTypeResponse)
async def update_meal_type(
    meal_type_id: UUID,
    meal_type_data: MealTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update meal type"""
    meal_type = db.query(MealType).filter(MealType.id == meal_type_id).first()
    if not meal_type:
        raise HTTPException(status_code=404, detail="Meal type not found")

    update_dict = meal_type_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(meal_type, field, value)

    try:
        db.commit()
        db.refresh(meal_type)
        return meal_type
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Meal type with this name already exists")


@router.delete("/meal-types/{meal_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal_type(
    meal_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete meal type"""
    meal_type = db.query(MealType).filter(MealType.id == meal_type_id).first()
    if not meal_type:
        raise HTTPException(status_code=404, detail="Meal type not found")

    db.delete(meal_type)
    db.commit()
    return None


# ============= EVENT TEMPLATES =============

@router.get("/templates", response_model=List[EventTemplateResponse])
async def list_event_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all event templates"""
    templates = db.query(EventTemplate).order_by(EventTemplate.name.asc()).all()
    return templates


@router.get("/templates/{template_id}", response_model=EventTemplateResponse)
async def get_event_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get event template by ID"""
    template = db.query(EventTemplate).filter(EventTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Event template not found")
    return template


@router.post("/templates", response_model=EventTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_event_template(
    template_data: EventTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create new event template"""
    # Check if template with same name already exists
    existing = db.query(EventTemplate).filter(EventTemplate.name == template_data.name).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Template with name '{template_data.name}' already exists"
        )

    template = EventTemplate(**template_data.dict())
    try:
        db.add(template)
        db.commit()
        db.refresh(template)
        return template
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Failed to create template")


@router.patch("/templates/{template_id}", response_model=EventTemplateResponse)
async def update_event_template(
    template_id: UUID,
    template_data: EventTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update event template"""
    template = db.query(EventTemplate).filter(EventTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Event template not found")

    update_dict = template_data.dict(exclude_unset=True)

    # Check if name is being changed and if it conflicts
    if 'name' in update_dict and update_dict['name'] != template.name:
        existing = db.query(EventTemplate).filter(EventTemplate.name == update_dict['name']).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Template with name '{update_dict['name']}' already exists"
            )

    for field, value in update_dict.items():
        setattr(template, field, value)

    try:
        db.commit()
        db.refresh(template)
        return template
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Failed to update template")


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete event template"""
    template = db.query(EventTemplate).filter(EventTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Event template not found")

    db.delete(template)
    db.commit()
    return None
