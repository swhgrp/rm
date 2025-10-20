"""
EmployeePosition model - links employees to positions
"""

from sqlalchemy import Column, Integer, Date, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from hr.db.database import Base


class EmployeePosition(Base):
    """Employee Position Assignment - links employees to positions with pay info"""

    __tablename__ = "employee_positions"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)

    # Location (API reference, not FK - maintains microservices independence)
    location_id = Column(Integer, nullable=True)

    # Pay Info
    hourly_rate = Column(Numeric(10, 2))
    salary = Column(Numeric(10, 2), nullable=True)

    # Assignment Period
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    # Primary Position Flag
    is_primary = Column(Boolean, default=True)

    # Relationships
    employee = relationship("Employee", backref="position_assignments")
    position = relationship("Position", backref="assignments")

    def __repr__(self):
        return f"<EmployeePosition: Employee {self.employee_id} - Position {self.position_id}>"
