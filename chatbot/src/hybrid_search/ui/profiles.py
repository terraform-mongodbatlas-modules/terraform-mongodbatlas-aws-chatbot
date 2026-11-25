"""Chat profile registry: list registered collections and resolve a selection.

A collection is selectable when ``_chatbot_profiles`` holds a document whose
``_id`` is its name, plus the configured default collection, which is always
selectable so the app works before any document exists. Chainlit calls
``set_chat_profiles`` on every ``/project/settings`` load, so the listing is
cached in process for a short time.

Chainlit sends the profile name back as a query parameter and does not verify it,
so the name is a collection name that must match ``COLLECTION_NAME_PATTERN`` and
the registry before it reaches Mongo.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from hybrid_search import chatbot_profiles
from hybrid_search.chatbot_profiles import ChatbotProfile, DemoQuery
from hybrid_search.mongo import INGEST_STATE_SUFFIX, get_client
from hybrid_search.settings import HybridSearchSettings

PROFILE_CACHE_TTL_S = 30.0
# The name travels as a query parameter and as a collection name, so keep it to
# characters that need no escaping and stay out of `system.` and `db.coll`.
COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_UNAUTHORIZED_CODE = 13

COLLECTION_SCOPED_GRANT_MESSAGE = (
    "This deployment's database user can read only one collection, so the other "
    "chat profiles are hidden. Remove `db_access.collection_name` from the module "
    "inputs to serve every profile in the database."
)


@dataclass(frozen=True)
class CollectionProfile:
    collection: str
    display_name: str
    description: str | None = None
    icon: str | None = None
    queries: tuple[DemoQuery, ...] = field(default_factory=tuple)
    system_prompt: str | None = None
    default: bool = False


@dataclass(frozen=True)
class ProfileListing:
    profiles: list[CollectionProfile]
    auth_limited: bool = False

    @property
    def default(self) -> CollectionProfile:
        return next(profile for profile in self.profiles if profile.default)

    def by_collection(self) -> dict[str, CollectionProfile]:
        return {profile.collection: profile for profile in self.profiles}


@dataclass(frozen=True)
class ProfileResolution:
    profile: CollectionProfile
    rejected_name: str | None = None


async def list_profiles(
    database: AsyncIOMotorDatabase,
    *,
    default_collection: str,
) -> ProfileListing:
    try:
        registry = await chatbot_profiles.load_registry(
            database[chatbot_profiles.PROFILES_COLLECTION]
        )
    except OperationFailure as exc:
        if exc.code != _UNAUTHORIZED_CODE:
            raise
        # A collection-scoped grant cannot read the registry, so only the default
        # stays selectable, under its collection name.
        return ProfileListing(
            profiles=[_profile(default_collection, None, default=True)],
            auth_limited=True,
        )
    default = _profile(default_collection, registry.get(default_collection), default=True)
    registered = [
        _profile(name, config)
        for name, config in registry.items()
        if name != default_collection
        and COLLECTION_NAME_PATTERN.match(name)
        and not name.endswith(INGEST_STATE_SUFFIX)
    ]
    registered.sort(key=lambda profile: (profile.display_name.lower(), profile.collection))
    return ProfileListing(profiles=[default, *registered])


def resolve_profile(name: str | None, listing: ProfileListing) -> ProfileResolution:
    default = listing.default
    if not name:
        return ProfileResolution(profile=default)
    if not isinstance(name, str) or not COLLECTION_NAME_PATTERN.match(name):
        return ProfileResolution(profile=default, rejected_name=str(name))
    profile = listing.by_collection().get(name)
    if profile is None:
        return ProfileResolution(profile=default, rejected_name=name)
    return ProfileResolution(profile=profile)


def rejected_profile_message(resolution: ProfileResolution) -> str:
    return (
        f'Chat profile "{resolution.rejected_name}" is unavailable. '
        f'Using "{resolution.profile.collection}" instead.'
    )


def _profile(
    name: str,
    config: ChatbotProfile | None,
    *,
    default: bool = False,
) -> CollectionProfile:
    return CollectionProfile(
        collection=name,
        display_name=config.display_name if config else name,
        description=config.description if config else None,
        icon=config.icon if config else None,
        queries=tuple(config.queries) if config else (),
        system_prompt=config.system_prompt if config else None,
        default=default,
    )


_cache_key: tuple[str, str] | None = None
_cached_at = 0.0
_cached_listing: ProfileListing | None = None


def clear_profile_cache() -> None:
    global _cache_key, _cached_at, _cached_listing
    _cache_key = None
    _cached_at = 0.0
    _cached_listing = None


async def load_profile_listing(
    settings: HybridSearchSettings,
    *,
    client: AsyncIOMotorClient | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ProfileListing:
    cached = _cache_get(settings, clock)
    if cached is not None:
        return cached
    owned = client is None
    if client is None:
        client = get_client(settings)
    try:
        listing = await list_profiles(
            client[settings.mongodb_database],
            default_collection=settings.chunks_collection,
        )
    finally:
        if owned:
            client.close()
    _cache_set(settings, listing, clock)
    return listing


def _cache_key_for(settings: HybridSearchSettings) -> tuple[str, str]:
    return (settings.mongodb_database, settings.chunks_collection)


def _cache_get(
    settings: HybridSearchSettings,
    clock: Callable[[], float],
) -> ProfileListing | None:
    if _cached_listing is None or _cache_key != _cache_key_for(settings):
        return None
    if clock() - _cached_at > PROFILE_CACHE_TTL_S:
        return None
    return _cached_listing


def _cache_set(
    settings: HybridSearchSettings,
    listing: ProfileListing,
    clock: Callable[[], float],
) -> None:
    global _cache_key, _cached_at, _cached_listing
    _cache_key = _cache_key_for(settings)
    _cached_at = clock()
    _cached_listing = listing
