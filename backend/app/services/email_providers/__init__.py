"""Email-provider registry. Resolve a provider by its stored key."""
from app.services.email_providers.base import EmailProvider
from app.services.email_providers.gmail import GmailProvider

_PROVIDERS: dict[str, EmailProvider] = {
    "google": GmailProvider(),
}


def get_provider(name: str) -> EmailProvider:
    """Return the provider for a connection's ``provider`` value."""
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown email provider: {name!r}")


__all__ = ["EmailProvider", "GmailProvider", "get_provider"]
