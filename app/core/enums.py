from enum import Enum


class Role(str, Enum):
    USER = "USER"
    REVIEWER = "REVIEWER"


class RequestStatus(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
