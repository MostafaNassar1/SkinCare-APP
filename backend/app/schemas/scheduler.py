from pydantic import BaseModel


class SchedulerRunOut(BaseModel):
    routine_reminders: int
    appointment_reminders: int
    forecasts: int
    pushes_sent: int
