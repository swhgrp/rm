"""
Employee model for HR Management System
"""

from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, Text, Table, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from hr.db.database import Base
from hr.core.encryption import get_encryption


# Association table for employee-location many-to-many relationship
employee_locations = Table(
    'employee_locations',
    Base.metadata,
    Column('employee_id', Integer, ForeignKey('employees.id', ondelete='CASCADE'), primary_key=True),
    Column('location_id', Integer, ForeignKey('locations.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default=func.now())
)


class Employee(Base):
    """Employee model - stores employee information"""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_number = Column(String, unique=True, nullable=False, index=True)

    # Basic Info
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    middle_name = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    email = Column(String, unique=True, nullable=True, index=True)
    _phone_number = Column('phone_number', String)  # Encrypted field

    # Address (Encrypted fields)
    _street_address = Column('street_address', String)
    _city = Column('city', String)
    _state = Column('state', String)
    _zip_code = Column('zip_code', String)

    # Emergency Contact (Encrypted fields)
    _emergency_contact_name = Column('emergency_contact_name', String)
    _emergency_contact_phone = Column('emergency_contact_phone', String)
    _emergency_contact_relationship = Column('emergency_contact_relationship', String)

    # Employment Info
    hire_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True)
    employment_status = Column(String, default="Active", nullable=False)  # Active, On Leave, Terminated
    employee_type = Column(String, default="Part-Time")  # Full-Time, Part-Time, Contractor
    starting_pay_rate = Column(Numeric(10, 2), nullable=True)  # Starting hourly/salary rate
    position_id = Column(Integer, ForeignKey('positions.id', ondelete='SET NULL'), nullable=True, index=True)

    # Termination Details
    termination_type = Column(String, nullable=True)  # "Voluntary" or "Involuntary"
    termination_reason = Column(Text, nullable=True)  # Detailed explanation
    final_decision_date = Column(Date, nullable=True)  # When termination was approved
    authorized_by = Column(String, nullable=True)  # Person who authorized termination

    # Integration Fields (for future phases)
    clover_employee_id = Column(String, unique=True, nullable=True, index=True)
    clover_synced_at = Column(DateTime(timezone=True), nullable=True)
    inventory_user_id = Column(Integer, nullable=True, index=True)
    inventory_sync_enabled = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, nullable=True)  # User ID who created

    # Relationships
    assigned_locations = relationship("Location", secondary=employee_locations, backref="employees")
    position = relationship("Position", backref="employees")

    # Encrypted field properties - transparent encryption/decryption
    @hybrid_property
    def phone_number(self):
        """Decrypt phone number when accessed."""
        try:
            return get_encryption().decrypt(self._phone_number)
        except Exception:
            return self._phone_number

    @phone_number.setter
    def phone_number(self, value):
        """Encrypt phone number when set."""
        if value:
            self._phone_number = get_encryption().encrypt(value)
        else:
            self._phone_number = None

    @hybrid_property
    def street_address(self):
        """Decrypt street address when accessed."""
        try:
            return get_encryption().decrypt(self._street_address)
        except Exception:
            return self._street_address

    @street_address.setter
    def street_address(self, value):
        """Encrypt street address when set."""
        if value:
            self._street_address = get_encryption().encrypt(value)
        else:
            self._street_address = None

    @hybrid_property
    def city(self):
        """Decrypt city when accessed."""
        try:
            return get_encryption().decrypt(self._city)
        except Exception:
            return self._city

    @city.setter
    def city(self, value):
        """Encrypt city when set."""
        if value:
            self._city = get_encryption().encrypt(value)
        else:
            self._city = None

    @hybrid_property
    def state(self):
        """Decrypt state when accessed."""
        try:
            return get_encryption().decrypt(self._state)
        except Exception:
            return self._state

    @state.setter
    def state(self, value):
        """Encrypt state when set."""
        if value:
            self._state = get_encryption().encrypt(value)
        else:
            self._state = None

    @hybrid_property
    def zip_code(self):
        """Decrypt zip code when accessed."""
        try:
            return get_encryption().decrypt(self._zip_code)
        except Exception:
            return self._zip_code

    @zip_code.setter
    def zip_code(self, value):
        """Encrypt zip code when set."""
        if value:
            self._zip_code = get_encryption().encrypt(value)
        else:
            self._zip_code = None

    @hybrid_property
    def emergency_contact_name(self):
        """Decrypt emergency contact name when accessed."""
        try:
            return get_encryption().decrypt(self._emergency_contact_name)
        except Exception:
            return self._emergency_contact_name

    @emergency_contact_name.setter
    def emergency_contact_name(self, value):
        """Encrypt emergency contact name when set."""
        if value:
            self._emergency_contact_name = get_encryption().encrypt(value)
        else:
            self._emergency_contact_name = None

    @hybrid_property
    def emergency_contact_phone(self):
        """Decrypt emergency contact phone when accessed."""
        try:
            return get_encryption().decrypt(self._emergency_contact_phone)
        except Exception:
            return self._emergency_contact_phone

    @emergency_contact_phone.setter
    def emergency_contact_phone(self, value):
        """Encrypt emergency contact phone when set."""
        if value:
            self._emergency_contact_phone = get_encryption().encrypt(value)
        else:
            self._emergency_contact_phone = None

    @hybrid_property
    def emergency_contact_relationship(self):
        """Decrypt emergency contact relationship when accessed."""
        try:
            return get_encryption().decrypt(self._emergency_contact_relationship)
        except Exception:
            return self._emergency_contact_relationship

    @emergency_contact_relationship.setter
    def emergency_contact_relationship(self, value):
        """Encrypt emergency contact relationship when set."""
        if value:
            self._emergency_contact_relationship = get_encryption().encrypt(value)
        else:
            self._emergency_contact_relationship = None

    def __repr__(self):
        return f"<Employee {self.employee_number}: {self.first_name} {self.last_name}>"
