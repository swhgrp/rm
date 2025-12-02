"""Clients API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
import logging

from events.core.database import get_db
from events.core.deps import require_auth, require_permission
from events.models import Client, Event, User
from events.schemas.client import ClientCreate, ClientUpdate, ClientResponse

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
