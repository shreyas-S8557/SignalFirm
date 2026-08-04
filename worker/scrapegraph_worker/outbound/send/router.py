from __future__ import annotations

from ...config import OutboundSettings
from ..models import MessageChannel
from .base import SendAdapter
from .email_adapter import EmailSendAdapter
from .linkedin_adapter import LinkedInSendAdapter
from .manual_adapter import ManualOnlyAdapter


def get_adapter(channel: MessageChannel, settings: OutboundSettings) -> SendAdapter:
    if channel in (MessageChannel.LINKEDIN_CONNECTION, MessageChannel.LINKEDIN_MESSAGE):
        return LinkedInSendAdapter()
    if channel in (MessageChannel.EMAIL, MessageChannel.MEETING_REQUEST):
        return EmailSendAdapter(settings)
    return ManualOnlyAdapter()
