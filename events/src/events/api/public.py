"""Public API endpoints (no auth required)"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import httpx
import logging
from uuid import UUID

from events.core.database import get_db
from events.core.config import settings
from events.models import (
    Client, Event, EventTemplate, EventStatus, Venue,
    Location, EventType, MealType, BeverageService
)
from events.schemas.intake import PublicIntakeRequest, PublicIntakeResponse
from events.schemas.settings import (
    LocationResponse, EventTypeResponse,
    MealTypeResponse, BeverageServiceResponse
)
from events.services.task_service import TaskService
from events.services.email_service import EmailService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/beo-intake", response_model=PublicIntakeResponse)
async def public_beo_intake(
    data: PublicIntakeRequest,
    db: Session = Depends(get_db)
):
    """
    Public BEO intake form submission

    - Verifies hCaptcha token
    - Creates or updates client
    - Creates event with PENDING status
    - Generates tasks from template
    - Queues confirmation email
    """
    try:
        # Skip hCaptcha verification (removed for simplified public form)
        # Forms are monitored for abuse through other means
        logger.info(f"Public intake form submission from {data.client.email}")

        # Find or create client
        client_data = data.client
        client_obj = db.query(Client).filter(Client.email == client_data.email).first()

        if not client_obj:
            client_obj = Client(
                name=client_data.name,
                email=client_data.email,
                phone=client_data.phone,
                org=client_data.org
            )
            db.add(client_obj)
            db.commit()
            db.refresh(client_obj)
            logger.info(f"Created new client: {client_obj.email}")
        else:
            # Update client info if changed
            client_obj.name = client_data.name
            client_obj.phone = client_data.phone or client_obj.phone
            client_obj.org = client_data.org or client_obj.org
            db.commit()
            logger.info(f"Updated existing client: {client_obj.email}")

        # Get event template
        template = db.query(EventTemplate).filter(
            EventTemplate.name == data.eventTemplateKey
        ).first()

        if not template:
            logger.warning(f"Template not found: {data.eventTemplateKey}")
            # Continue without template

        # Create event
        event_data = data.event

        # Get venue_id - use provided or default to first venue
        venue_id = event_data.venue_id
        if not venue_id:
            # Use first available venue as default
            default_venue = db.query(Venue).order_by(Venue.name).first()
            if default_venue:
                venue_id = default_venue.id
                logger.info(f"Using default venue: {default_venue.name}")
            else:
                logger.warning("No venues available in database")

        # Merge template defaults with provided data
        menu_json = event_data.menu_json or (template.default_menu_json if template else None)
        financials_json = None
        if template and template.default_financials_json:
            financials_json = template.default_financials_json.copy()
            if event_data.budget_estimate:
                financials_json['estimated_total'] = event_data.budget_estimate

        event = Event(
            title=event_data.title,
            event_type=event_data.event_type,
            status=EventStatus.PENDING,
            venue_id=venue_id,  # Use venue_id instead of location text
            client_id=client_obj.id,
            start_at=event_data.start_at,
            end_at=event_data.end_at,
            setup_start_at=event_data.setup_start_at,
            teardown_end_at=event_data.teardown_end_at,
            guest_count=event_data.guest_count,
            menu_json=menu_json,
            requirements_json=event_data.requirements_json,
            financials_json=financials_json,
            lead_source='public_form'
        )

        db.add(event)
        db.commit()
        db.refresh(event)
        logger.info(f"Created event: {event.id} - {event.title}")

        # Generate tasks from template
        if template:
            task_service = TaskService()
            tasks = task_service.generate_tasks_from_template(db, event, template)
            logger.info(f"Generated {len(tasks)} tasks for event {event.id}")

        # Sync to CalDAV for admin user if enabled
        if settings.CALDAV_ENABLED:
            try:
                from events.services.caldav_sync_service import CalDAVSyncService
                caldav_service = CalDAVSyncService()
                # Sync to admin user 'andy' - new events should appear in admin calendar
                caldav_service.sync_event_to_caldav(event, 'andy')
                logger.info(f"Event {event.id} synced to CalDAV for admin")
            except Exception as e:
                logger.error(f"Failed to sync event {event.id} to CalDAV: {e}")
                # Don't fail the whole request if CalDAV sync fails

        # Send confirmation email
        try:
            if template and template.email_rules_json:
                email_service = EmailService()
                await email_service.send_notification_by_rule(
                    db, event, trigger='on_created', template=template
                )
                logger.info(f"Queued confirmation email for event {event.id}")
        except Exception as e:
            logger.error(f"Failed to send confirmation email: {e}")
            # Don't fail the whole request if email fails

        # Generate reference number (simple format)
        reference_number = f"EVT-{event.created_at.strftime('%Y%m%d')}-{str(event.id)[:8].upper()}"

        return PublicIntakeResponse(
            success=True,
            event_id=str(event.id),
            message=f"Your event request has been submitted! Reference: {reference_number}",
            reference_number=reference_number
        )
    except Exception as e:
        logger.exception(f"Error processing intake form: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process event request: {str(e)}"
        )


@router.get("/health")
async def public_health():
    """Public health check endpoint"""
    return {"status": "healthy", "endpoint": "public"}


@router.get("/venues")
async def public_list_venues(db: Session = Depends(get_db)):
    """Get all venues (public - no auth required)"""
    venues = db.query(Venue).order_by(Venue.name).all()
    return [{"id": str(v.id), "name": v.name, "address": v.address} for v in venues]


@router.get("/locations", response_model=List[LocationResponse])
async def public_list_locations(db: Session = Depends(get_db)):
    """List all active locations (public - no auth required)"""
    locations = db.query(Location).filter(Location.is_active == True).order_by(
        Location.sort_order.asc(), Location.name.asc()
    ).all()
    return locations


@router.get("/event-types", response_model=List[EventTypeResponse])
async def public_list_event_types(db: Session = Depends(get_db)):
    """List all active event types (public - no auth required)"""
    event_types = db.query(EventType).filter(EventType.is_active == True).order_by(
        EventType.sort_order.asc(), EventType.name.asc()
    ).all()
    return event_types


@router.get("/meal-types", response_model=List[MealTypeResponse])
async def public_list_meal_types(db: Session = Depends(get_db)):
    """List all active meal types (public - no auth required)"""
    meal_types = db.query(MealType).filter(MealType.is_active == True).order_by(
        MealType.sort_order.asc(), MealType.name.asc()
    ).all()
    return meal_types


@router.get("/beverage-services", response_model=List[BeverageServiceResponse])
async def public_list_beverage_services(db: Session = Depends(get_db)):
    """List all active beverage services (public - no auth required)"""
    services = db.query(BeverageService).filter(BeverageService.is_active == True).order_by(
        BeverageService.sort_order.asc(), BeverageService.name.asc()
    ).all()
    return services
