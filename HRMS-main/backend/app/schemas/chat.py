from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)


class ChatMessageCreate(BaseModel):
    role: str = Field(min_length=3, max_length=20)
    content: str = Field(min_length=1, max_length=4000)


class ChatTestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class PolicyChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SQLChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ActionChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=1000)


class RouterChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=1, max_length=100)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=8)
