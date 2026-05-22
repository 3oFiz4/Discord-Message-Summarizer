"""
MessageDTO model
    # identity
    message_id: int
    channel_id: int
    guild_id: Optional[int]
    # author
    author_id: int
    # content
    content: str
    # timestamps
    created_at: datetime
    edited_at: Optional[datetime]
    # relationships
    reply_to_message_id: Optional[int]
    # media
    attachment_urls: Optionla[list[str]]

    f:__post_init__() 
    # Validates each give attribute and give Panic() if it is invalid.

MessageCollection object.
 f:execute(command: SQLCommand)
 # Simple CRUD operation, use f:execute if it's complex.
 f:create(message: MessageDTO, position: index|top|bottom) -> execute
 f:read() -> List[MessageDTO]
 f:update(message_id: MessageDTO.id, newMessage: MessageDTO)
 f:delete(position: index|top|bottom)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Iterator, Optional

import discord as dc

@dataclass(frozen=True, slots=True)
class MessageDTO:
    # Position attr
    message_id: int
    channel_id: int
    guild_id: Optional[int]

    # Author attr
    author_id: int

    # Content attr
    content: str

    # Date attr
    created_at: Optinal[datetime] # optional, but useful if provided
    edited_at: Optional[datetime] # might remove this soon?

    # Relationship attr
    # This might be useful in the future. Considering when the message- 
    # context is within the reply. Let this be a future consideration.
    # TODO:: Let this object to be able to retrieve the content of replied message
    reply_to_message_id: Optional[int]

    # Media attr
    attachment_urls: list[str] = field(default_factory=list)

# INFO: Ensure everytime this object is used, all attribute are provided, if the given attribute value cannot be existing, assign None.
msg1 = MessageDTO(
        message_id=1,
        channel_id=10,
        guild_id=999,
        author_id=1001,
        content="Hello everyone!",
        created_at=datetime(2026, 5, 22, 10, 0, 0),
        edited_at=None,
        reply_to_message_id=None,
        attachment_urls=[],
    )
print(msg1)
