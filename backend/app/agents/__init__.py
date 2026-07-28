
from app.agents.review import register_reviewer
from app.agents.profile_agent import profile_reviewer
from app.agents.intervention_agent import intervention_reviewer
from app.agents.schedule_agent import schedule_reviewer

register_reviewer("profile_agent", profile_reviewer)
register_reviewer("intervention_agent", intervention_reviewer)
register_reviewer("schedule_agent", schedule_reviewer)

__all__ = ["register_reviewer"]
