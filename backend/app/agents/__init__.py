
from app.agents.review import register_reviewer
from app.agents.profile_agent import profile_reviewer

register_reviewer("profile_agent", profile_reviewer)

__all__ = ["register_reviewer"]
