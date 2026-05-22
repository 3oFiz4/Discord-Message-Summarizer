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
from services.helper.error_logger import Panic

@dataclass(frozen=True, slots=True)
class MessageDTO:
    """Model for Message
    .name: str= to get author name (require: author_id)
    .is_edited: bool = *self-explanatory* (require: edited_at)
    .has_attachments: bool = *self-explanatory* (require: attachment_urls)
    .to_dict: dict[str, Any] = converts the object itself to dict version // This is useful for MessageCollection
    """
    id: Optional[int] # None, but auto-increment in MessageCollection
    
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

    def __post_init__(self) -> None:
            """Self-validation after object creation."""
            self._validate_optional_positive_int("id", self.id)
            self._validate_positive_int("message_id", self.message_id)
            self._validate_positive_int("channel_id", self.channel_id)
            self._validate_optional_positive_int("guild_id", self.guild_id)
            self._validate_positive_int("author_id", self.author_id)

            self._validate_string("content", self.content)

            self._validate_datetime("created_at", self.created_at)
            self._validate_optional_datetime("edited_at", self.edited_at)

            self._validate_optional_positive_int(
                "reply_to_message_id",
                self.reply_to_message_id,
            )

            self._validate_attachment_urls(self.attachment_urls)
            self._validate_business_rules()

    # -------------------------
    # Derived / readable fields
    # -------------------------
    @property
    def name(self) -> str:
        """TODO: Implement author_id resolver by using module discord. This property not working for now."""
        """Readable name derived from author_id."""
        return self._resolve_author_name()

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None

    @property
    def has_attachments(self) -> bool:
        return len(self.attachment_urls) > 0
    
    @property
    def to_dict(self) -> dict[str, Any]:
        """Flat this object to dict, necessary for MessageColection later"""
        _dict = {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "author_id": self.author_id,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "reply_to_message_id": self.reply_to_message_id,
            "attachment_urls": ",".join(self.attachment_urls) if self.attachment_urls else "",
        }
        # Only include id if explicitly set (otherwise let DB auto-increment)
        if self.id is not None:
            _dict["id"] = self.id
        return _dict

    # -------------------------
    # Private helpers
    # -------------------------
    def _resolve_author_name(self) -> str:
        return self._AUTHOR_DIRECTORY.get(self.author_id, f"User#{self.author_id}")

    def _validate_positive_int(self, field_name: str, value: object) -> None:
        #TODO: Add another function that checks whether the id actually exist, requires Discord to be initialized with a given token. 
        if not isinstance(value, int) or isinstance(value, bool):
            Panic(
                TypeError,
                f"Invalid {field_name} type: {type(value).__name__}",
                solutions=[
                    f"Pass an integer for '{field_name}'",
                    f"Use a positive numeric ID, e.g. {field_name}=123",
                ],
                note=f"MessageDTO {field_name} type validation failed",
            )

        if value <= 0:
            Panic(
                ValueError,
                f"'{field_name}' must be greater than 0, got {value}",
                solutions=[
                    f"Use a positive integer for '{field_name}'",
                    "Make sure the ID is a valid database/platform ID",
                ],
                note=f"MessageDTO {field_name} value validation failed",
            )

    def _validate_optional_positive_int(self, field_name: str, value: object) -> None:
        if value is None:
            return
        self._validate_positive_int(field_name, value)

    def _validate_string(self, field_name: str, value: object) -> None:
        if not isinstance(value, str):
            Panic(
                TypeError,
                f"Invalid {field_name} type: {type(value).__name__}",
                solutions=[
                    f"Pass a string for '{field_name}'",
                    "Convert the value to str before creating MessageDTO",
                ],
                note=f"MessageDTO {field_name} type validation failed",
            )

    def _validate_datetime(self, field_name: str, value: object) -> None:
        if not isinstance(value, datetime):
            Panic(
                TypeError,
                f"Invalid {field_name} type: {type(value).__name__}",
                solutions=[
                    f"Pass a datetime object for '{field_name}'",
                    "Example: datetime.now()",
                ],
                note=f"MessageDTO {field_name} type validation failed",
            )

    def _validate_optional_datetime(self, field_name: str, value: object) -> None:
        if value is None:
            return
        self._validate_datetime(field_name, value)

    def _validate_attachment_urls(self, value: object) -> None:
        if not isinstance(value, list):
            Panic(
                TypeError,
                f"Invalid attachment_urls type: {type(value).__name__}",
                solutions=[
                    "Pass a list of strings",
                    "Use [] if there are no attachments",
                    "Example: ['https://example.com/file.png']",
                ],
                note="MessageDTO attachment_urls validation failed",
            )

        for index, item in enumerate(value):
            if not isinstance(item, str):
                Panic(
                    TypeError,
                    f"attachment_urls[{index}] must be str, got {type(item).__name__}",
                    solutions=[
                        "Ensure each attachment URL is a string",
                        "Convert URL objects to str before passing them",
                    ],
                    note="MessageDTO attachment_urls item validation failed",
                )

            if not item.startswith(("http://", "https://")):
                Panic(
                    ValueError,
                    f"attachment_urls[{index}] is not a valid URL: {item}",
                    solutions=[
                        "Use URLs starting with http:// or https://",
                        "Check the attachment source before creating MessageDTO",
                    ],
                    note="MessageDTO attachment URL format validation failed",
                )

    def _validate_business_rules(self) -> None:
        if self.edited_at is not None and self.edited_at < self.created_at:
            Panic(
                ValueError,
                f"'edited_at' ({self.edited_at}) cannot be earlier than "
                f"'created_at' ({self.created_at})",
                solutions=[
                    "Make edited_at later than or equal to created_at",
                    "Use None if the message was never edited",
                ],
                note="MessageDTO timestamp rule validation failed",
            )

        if (
            self.reply_to_message_id is not None
            and self.reply_to_message_id == self.message_id
        ):
            Panic(
                ValueError,
                "A message cannot reply to itself",
                solutions=[
                    "Use another message ID in reply_to_message_id",
                    "Use None if this is not a reply",
                ],
                note="MessageDTO reply relationship validation failed",
            )


# INFO: Ensure everytime this object is used, all attribute are provided, if the given attribute value cannot be existing, assign None.
# msg1 = MessageDTO(
#         message_id="stop",
#         channel_id=10,
#         guild_id=999,
#         author_id=1001,
#         content="Hello everyone!",
#         created_at=datetime(2026, 5, 22, 10, 0, 0),
#         edited_at=None,
#         reply_to_message_id=None,
#         attachment_urls=[],
#     )
# print(msg1)
