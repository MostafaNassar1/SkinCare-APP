from pydantic import BaseModel


class SchedulerRunOut(BaseModel):
    routine_reminders: int
    appointment_reminders: int
    pushes_sent: int
