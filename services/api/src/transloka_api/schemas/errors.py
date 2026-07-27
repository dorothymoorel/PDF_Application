from pydantic import BaseModel

type ErrorDetails = dict[str, object]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: ErrorDetails
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
