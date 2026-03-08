from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import SupportTicket


class SupportTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_telegram_id: int,
        user_name: str | None,
        message: str,
    ) -> SupportTicket:
        ticket = SupportTicket(
            user_telegram_id=user_telegram_id,
            user_name=user_name,
            message=message,
        )
        self.session.add(ticket)
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def set_reply(
        self,
        ticket_id: int,
        reply: str,
        admin_telegram_id: int,
    ) -> None:
        ticket = await self.session.get(SupportTicket, ticket_id)
        if ticket:
            ticket.reply = reply
            ticket.admin_telegram_id = admin_telegram_id
            ticket.replied_at = datetime.utcnow()
            await self.session.commit()
