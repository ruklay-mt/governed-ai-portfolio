"""The four demo personas (spec §4.2) and the database login each one uses (ADR 0008)."""

from dataclasses import dataclass

from pydantic import SecretStr

from app.config import Settings


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    title: str
    location: str
    region: str | None  # None = all regions
    role: str  # NOLOGIN persona role holding the grants
    login: str  # LOGIN user the API connects as

    def password(self, settings: Settings) -> SecretStr | None:
        value: SecretStr | None = getattr(settings, f"agent_db_password_{self.id}")
        return value


# Must match ops.persona_scope and the logins in data/sql/migrations/0003_roles.sql
# (a DB test checks this).
PERSONAS: dict[str, Persona] = {
    persona.id: persona
    for persona in (
        Persona(
            id="sales_rep_nz_south",
            name="Mia Tane",
            title="Sales rep",
            location="Christchurch",
            region="NZ-SOUTH",
            role="r_sales_rep",
            login="agent_sales_rep_nz_south",
        ),
        Persona(
            id="sales_manager",
            name="Liam Chen",
            title="Sales manager",
            location="Auckland",
            region=None,
            role="r_sales_manager",
            login="agent_sales_manager",
        ),
        Persona(
            id="finance",
            name="Raj Patel",
            title="Finance",
            location="Sydney",
            region=None,
            role="r_finance",
            login="agent_finance",
        ),
        Persona(
            id="support",
            name="Sophie Williams",
            title="Support agent",
            location="Melbourne",
            region=None,
            role="r_support",
            login="agent_support",
        ),
    )
}


def get_persona(persona_id: str) -> Persona:
    try:
        return PERSONAS[persona_id]
    except KeyError:
        raise ValueError(f"unknown persona {persona_id!r}") from None
