"""The version of the identity-provider contract this platform speaks.

A provider in a separate distribution is written against whatever
:class:`~glossogen.server.identity.identity_provider.IdentityProvider` looked like
at the time. Adding an abstract method to that contract already fails loudly,
because the class cannot be instantiated. A method whose meaning changes while its
signature does not will not fail at all, and for an authentication contract the
failure mode of that is a provider that accepts credentials it should reject.

The version therefore lives in the entry-point group name a plug-in declares
itself under, ``glossogen.identity_provider.v1``, not in an attribute on the class.
A class attribute cannot work: an external subclass that does not set one inherits
it from the installed platform's base class, so it reports whatever version is
running and never disagrees with it. Only a string the author writes into their own
metadata records what they built against.

Bumping this number stops a platform reading the older group. Unlike a scenario or
a metric, a provider declared under an unread group is not treated as absent:
:func:`~glossogen.server.identity.identity_provider_loader.load_identity_provider`
refuses to boot, because a server that silently falls back to single-tenant mode
performs no authentication at all.
"""

IDENTITY_API_VERSION = 1
