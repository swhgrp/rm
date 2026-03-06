"""Document generation API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from events.core.database import get_db
from events.core.deps import require_auth, check_permission
from events.models import Event, Document, DocumentType, User
from events.services.pdf_service import PDFService

router = APIRouter()
pdf_service = PDFService()


@router.get("/events/{event_id}/beo-pdf")
async def generate_beo_pdf(
    event_id: UUID,
    download: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Generate BEO (Banquet Event Order) PDF for an event

    - **event_id**: Event UUID
    - **download**: If true, returns as downloadable file (default: true)
    """
    # Permission check
    if not check_permission(current_user, "read", "document"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to generate documents"
        )

    from sqlalchemy.orm import joinedload

    # Get event with related data
    event = db.query(Event).options(
        joinedload(Event.client),
        joinedload(Event.venue)
    ).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Generate PDF
    try:
        pdf_bytes = pdf_service.generate_beo_pdf(
            event=event,
            client=event.client,
            venue=event.venue
        )

        # Create document record (optional - for tracking purposes)
        try:
            document = Document(
                event_id=event_id,
                doc_type=DocumentType.BEO,
                storage_url=f"generated/beo_{event_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            db.add(document)
            db.commit()
        except Exception:
            # Document tracking is optional, don't fail PDF generation
            db.rollback()

        # Return PDF
        filename = f"BEO_{event.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        headers = {
            'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'
        }

        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers=headers
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )


@router.get("/events/{event_id}/contract-pdf")
async def generate_contract_pdf(
    event_id: UUID,
    download: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Generate Catering Contract PDF for an event"""
    if not check_permission(current_user, "read", "document"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to generate documents"
        )

    from sqlalchemy.orm import joinedload

    event = db.query(Event).options(
        joinedload(Event.client),
        joinedload(Event.venue)
    ).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    try:
        pdf_bytes = pdf_service.generate_catering_contract_pdf(
            event=event,
            client=event.client,
            venue=event.venue
        )

        try:
            document = Document(
                event_id=event_id,
                doc_type=DocumentType.CONTRACT,
                storage_url=f"generated/contract_{event_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            db.add(document)
            db.commit()
        except Exception:
            db.rollback()

        filename = f"Contract_{event.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        headers = {
            'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'
        }

        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers=headers
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )


@router.get("/events/{event_id}/summary-pdf")
async def generate_event_summary_pdf(
    event_id: UUID,
    download: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Generate event summary PDF with task list

    - **event_id**: Event UUID
    - **download**: If true, returns as downloadable file (default: true)
    """
    # Permission check
    if not check_permission(current_user, "read", "document"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to generate documents"
        )

    from sqlalchemy.orm import joinedload
    from events.models import Task

    # Get event with related data
    event = db.query(Event).options(
        joinedload(Event.client),
        joinedload(Event.venue)
    ).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Get tasks for the event
    tasks = db.query(Task).filter(Task.event_id == event_id).all()

    # Generate PDF
    try:
        pdf_bytes = pdf_service.generate_event_summary_pdf(
            event=event,
            tasks=tasks
        )

        # Create document record (optional - for tracking purposes)
        try:
            document = Document(
                event_id=event_id,
                doc_type=DocumentType.SUMMARY,
                storage_url=f"generated/summary_{event_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            db.add(document)
            db.commit()
        except Exception:
            # Document tracking is optional, don't fail PDF generation
            db.rollback()

        # Return PDF
        filename = f"Summary_{event.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        headers = {
            'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'
        }

        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers=headers
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )
