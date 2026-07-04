from sqlalchemy import Column, String, Boolean, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin, gen_uuid
import enum


class Plan(str, enum.Enum):
    starter = "starter"
    growth = "growth"
    scale = "scale"


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    domain = Column(String(255))
    plan = Column(SAEnum(Plan), default=Plan.starter, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text)

    users = relationship("User", back_populates="workspace")
    repositories = relationship("Repository", back_populates="workspace")



class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="owner")
    is_active = Column(Boolean, default=True, nullable=False)

    workspace = relationship("Workspace", back_populates="users")
