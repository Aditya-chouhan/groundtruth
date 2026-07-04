from sqlalchemy import Column, String, Text, Float, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .base import Base, TimestampMixin, gen_uuid


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=gen_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False) # e.g. "mem0"
    owner = Column(String(255), nullable=False) # e.g. "mem0ai"
    branch = Column(String(255), default="main")
    status = Column(String(50), default="active") # active, indexing, paused

    workspace = relationship("Workspace", back_populates="repositories")
    activities = relationship("RepositoryActivity", back_populates="repository")
    rulebooks = relationship("RuleBook", back_populates="repository")
    findings = relationship("WebhookFinding", back_populates="repository")


class RepositoryActivity(Base, TimestampMixin):
    __tablename__ = "repository_activities"

    id = Column(String, primary_key=True, default=gen_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False, index=True)
    workspace_id = Column(String, nullable=False, index=True)
    activity_type = Column(String(50), nullable=False) # pr, commit, issue, review
    external_id = Column(String(255)) # GitHub ID or Number
    title = Column(String(500))
    author = Column(String(255))
    payload = Column(JSON, default=dict)
    raw_content = Column(Text)

    repository = relationship("Repository", back_populates="activities")


class RuleBook(Base, TimestampMixin):
    __tablename__ = "rulebooks"

    id = Column(String, primary_key=True, default=gen_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False, index=True)
    workspace_id = Column(String, nullable=False, index=True)
    filename = Column(String(255), nullable=False) # CLAUDE.md, SKILL.md, AGENTS.md
    content = Column(Text, nullable=False)
    version = Column(Float, default=1.0)
    is_current = Column(Boolean, default=True, nullable=False)

    repository = relationship("Repository", back_populates="rulebooks")


class WebhookFinding(Base, TimestampMixin):
    __tablename__ = "webhook_findings"

    id = Column(String, primary_key=True, default=gen_uuid)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False, index=True)
    workspace_id = Column(String, nullable=False, index=True)
    event_type = Column(String(50), nullable=False) # pull_request
    external_id = Column(String(255)) # PR number or commit hash
    severity = Column(String(50), default="info") # info, warning, error
    title = Column(String(500))
    details = Column(JSON, default=dict)
    checked_at = Column(Text)

    repository = relationship("Repository", back_populates="findings")


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    id = Column(String, primary_key=True, default=gen_uuid)
    workspace_id = Column(String, nullable=False, index=True)
    source_type = Column(String(100), nullable=False)   # repo_activity, rulebook
    source_id = Column(String)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, default=dict)
    embedding = Column(Vector(1536))
