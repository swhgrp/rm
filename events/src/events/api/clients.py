"""Clients API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
import logging

from events.core.database import get_db
from events.core.deps import require_auth, require_permission
from events.models import Client, Event, User
from events.schemas.client import ClientCreate, ClientUpdate, ClientResponse


class MergeClientsRequest(BaseModel):
    """Request body for merging clients"""
    primary_client_id: UUID
    secondary_client_ids: List[UUID]
    merge_notes: bool = True  # Whether to combine notes from all clients

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[ClientResponse])
async def list_clients(
    search: Optional[str] = Query(None, description="Search by name, email, or org"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List all clients with optional search filter

    Returns clients with their event counts
    """
    query = db.query(Client)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Client.name.ilike(search_term)) |
            (Client.email.ilike(search_term)) |
            (Client.org.ilike(search_term))
        )

    # Get clients with event counts using a subquery
    clients = query.order_by(Client.name).offset(skip).limit(limit).all()

    # Add event counts
    result = []
    for client in clients:
        event_count = db.query(func.count(Event.id)).filter(Event.client_id == client.id).scalar()
        client_dict = {
            "id": client.id,
            "name": client.name,
            "email": client.email,
            "phone": client.phone,
            "org": client.org,
            "notes": client.notes,
            "created_at": client.created_at,
            "updated_at": client.updated_at,
            "event_count": event_count or 0
        }
        result.append(client_dict)

    return result


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a single client by ID"""
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Add event count
    event_count = db.query(func.count(Event.id)).filter(Event.client_id == client.id).scalar()

    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "org": client.org,
        "notes": client.notes,
        "created_at": client.created_at,
        "updated_at": client.updated_at,
        "event_count": event_count or 0
    }


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Create a new client

    Requires authentication
    """
    # Check if email already exists
    existing = db.query(Client).filter(Client.email == client_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A client with email '{client_data.email}' already exists"
        )

    client = Client(**client_data.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)

    logger.info(f"Client created: {client.name} ({client.email}) by user {current_user.email}")

    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "org": client.org,
        "notes": client.notes,
        "created_at": client.created_at,
        "updated_at": client.updated_at,
        "event_count": 0
    }


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Update a client

    Requires authentication
    """
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Check if email is being changed to an existing one
    update_data = client_data.model_dump(exclude_unset=True)
    if "email" in update_data and update_data["email"] != client.email:
        existing = db.query(Client).filter(
            Client.email == update_data["email"],
            Client.id != client_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A client with email '{update_data['email']}' already exists"
            )

    # Apply updates
    for field, value in update_data.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)

    logger.info(f"Client updated: {client.name} ({client.email}) by user {current_user.email}")

    # Get event count
    event_count = db.query(func.count(Event.id)).filter(Event.client_id == client.id).scalar()

    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "org": client.org,
        "notes": client.notes,
        "created_at": client.created_at,
        "updated_at": client.updated_at,
        "event_count": event_count or 0
    }


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Delete a client

    Note: Will fail if client has associated events
    """
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Check if client has events
    event_count = db.query(func.count(Event.id)).filter(Event.client_id == client.id).scalar()
    if event_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete client with {event_count} associated event(s). Delete or reassign events first."
        )

    client_name = client.name
    client_email = client.email

    db.delete(client)
    db.commit()

    logger.info(f"Client deleted: {client_name} ({client_email}) by user {current_user.email}")

    return None


@router.get("/{client_id}/events")
async def get_client_events(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all events for a client"""
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    events = db.query(Event).filter(Event.client_id == client_id).order_by(Event.start_at.desc()).all()

    return [
        {
            "id": str(event.id),
            "title": event.title,
            "event_type": event.event_type,
            "status": event.status.value if event.status else None,
            "start_at": event.start_at.isoformat() if event.start_at else None,
            "end_at": event.end_at.isoformat() if event.end_at else None,
            "guest_count": event.guest_count,
            "venue_name": event.venue.name if event.venue else None
        }
        for event in events
    ]


@router.post("/merge", response_model=ClientResponse)
async def merge_clients(
    merge_request: MergeClientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Merge multiple clients into a primary client

    - Reassigns all events from secondary clients to the primary client
    - Optionally combines notes from all clients
    - Deletes secondary clients after merge
    """
    primary_id = merge_request.primary_client_id
    secondary_ids = merge_request.secondary_client_ids

    # Validate primary client exists
    primary_client = db.query(Client).filter(Client.id == primary_id).first()
    if not primary_client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Primary client not found"
        )

    # Validate secondary clients exist
    secondary_clients = db.query(Client).filter(Client.id.in_(secondary_ids)).all()
    if len(secondary_clients) != len(secondary_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more secondary clients not found"
        )

    # Ensure primary is not in secondary list
    if primary_id in secondary_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary client cannot be in the secondary clients list"
        )

    try:
        merged_info = []
        total_events_reassigned = 0

        for secondary in secondary_clients:
            # Count events being reassigned
            events_count = db.query(func.count(Event.id)).filter(
                Event.client_id == secondary.id
            ).scalar()
            total_events_reassigned += events_count

            # Reassign all events from secondary to primary
            db.query(Event).filter(Event.client_id == secondary.id).update(
                {Event.client_id: primary_id}
            )

            # Collect info for merged notes
            merged_info.append({
                'name': secondary.name,
                'email': secondary.email,
                'phone': secondary.phone,
                'org': secondary.org,
                'notes': secondary.notes,
                'events_count': events_count
            })

            logger.info(f"Reassigned {events_count} events from client {secondary.email} to {primary_client.email}")

        # Merge notes if requested
        if merge_request.merge_notes:
            notes_parts = []
            if primary_client.notes:
                notes_parts.append(primary_client.notes)

            for info in merged_info:
                merge_note = f"\n--- Merged from {info['name']} ({info['email']}) ---"
                if info['phone']:
                    merge_note += f"\nPhone: {info['phone']}"
                if info['org']:
                    merge_note += f"\nOrg: {info['org']}"
                if info['notes']:
                    merge_note += f"\nNotes: {info['notes']}"
                notes_parts.append(merge_note)

            if notes_parts:
                primary_client.notes = '\n'.join(notes_parts)

        # Delete secondary clients
        for secondary in secondary_clients:
            secondary_name = secondary.name
            secondary_email = secondary.email
            db.delete(secondary)
            logger.info(f"Deleted merged client: {secondary_name} ({secondary_email})")

        db.commit()
        db.refresh(primary_client)

        logger.info(
            f"Merged {len(secondary_clients)} client(s) into {primary_client.name} ({primary_client.email}), "
            f"reassigned {total_events_reassigned} event(s) - by user {current_user.email}"
        )

        # Get updated event count
        event_count = db.query(func.count(Event.id)).filter(
            Event.client_id == primary_client.id
        ).scalar()

        return {
            "id": primary_client.id,
            "name": primary_client.name,
            "email": primary_client.email,
            "phone": primary_client.phone,
            "org": primary_client.org,
            "notes": primary_client.notes,
            "created_at": primary_client.created_at,
            "updated_at": primary_client.updated_at,
            "event_count": event_count or 0
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"Error merging clients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to merge clients: {str(e)}"
        )
