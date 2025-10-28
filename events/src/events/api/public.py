"""Public API endpoints (no auth required)"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
import logging
from uuid import UUID

from events.core.database import get_db
from events.core.config import settings
from events.models import Client, Event, EventTemplate, EventStatus
from events.schemas.intake import PublicIntakeRequest, PublicIntakeResponse
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

    # Verify hCaptcha
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://hcaptcha.com/siteverify",
                data={
                    'secret': settings.HCAPTCHA_SECRET,
                    'response': data.hcaptcha_token
                },
                timeout=10.0
            )
            captcha_result = response.json()

            if not captcha_result.get('success'):
                logger.warning(f"hCaptcha verification failed: {captcha_result}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid captcha verification"
                )
    except httpx.TimeoutException:
        logger.error("hCaptcha verification timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Captcha verification service unavailable"
        )
    except Exception as e:
        logger.error(f"hCaptcha verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error verifying captcha"
        )

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
        venue_id=UUID(event_data.venue_id),
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


@router.get("/health")
async def public_health():
    """Public health check endpoint"""
    return {"status": "healthy", "endpoint": "public"}
