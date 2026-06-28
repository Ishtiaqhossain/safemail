"""Email-provider registry. Resolve a provider by its stored key."""
from app.services.email_providers.base import EmailProvider
from app.services.email_providers.gmail import GmailProvider
from app.services.email_providers.apple import AppleMailProvider

_PROVIDERS: dict[str, EmailProvider] = {
    "google": GmailProvider(),
    "apple": AppleMailProvider(),
}


def get_provider(name: str) -> EmailProvider:
    """Return the provider for a connection's ``provider`` value."""
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown email provider: {name!r}")


__all__ = ["EmailProvider", "GmailProvider", "AppleMailProvider", "get_provider"]
