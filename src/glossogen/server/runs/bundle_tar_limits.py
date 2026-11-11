"""Bounds on how much reading an uploaded run bundle's tar headers may cost.

``tarfile`` reads some headers whole into memory before it hands back the member they
describe: a GNU long name, a pax extended header, a GNU sparse map. Each one is sized
by the archive, so an upload of a few megabytes that gzip expands into gigabytes of
one header is read in full before any check on the members runs. Measured: a 1 MB
bundle holding one 1 GiB long-name header took the reading process to 7.7 GB.

:class:`BundleTarFile` refuses those headers past a budget before reading them, and
refuses the header types a bundle never carries.
"""

import tarfile
from collections.abc import Callable
from typing import cast

# Every member header read is held in memory as a TarInfo, and an empty member costs
# the uploader almost nothing once gzipped. A run bundle carries a run directory's
# files, and a legacy one also its ``.git`` objects; this sits well above both.
MAX_BUNDLE_MEMBER_COUNT: int = 50_000

# Long names and pax records across the whole archive. Python's default tar format
# writes a pax record of a few dozen bytes for each member with a fractional mtime, so
# this covers a bundle at the member ceiling.
MAX_BUNDLE_EXTENDED_HEADER_BYTES: int = 4 * 1024 * 1024

# Extended headers in a row before one member. ``tarfile`` recurses once for each, so
# a long chain of empty ones ends in a RecursionError. A writer puts at most a pax
# header, or a long name and a long link, before a member.
MAX_CONSECUTIVE_EXTENDED_HEADERS: int = 4

_EXTENDED_HEADER_TYPES: frozenset[bytes] = frozenset(
    {
        tarfile.GNUTYPE_LONGNAME,
        tarfile.GNUTYPE_LONGLINK,
        tarfile.XHDTYPE,
        tarfile.SOLARIS_XHDTYPE,
    }
)

# A global pax header is copied into every later member, and a sparse member's map
# is read block by block with no bound. ``build_bundle_bytes`` writes neither.
_REFUSED_HEADER_TYPES: frozenset[bytes] = frozenset({tarfile.XGLTYPE, tarfile.GNUTYPE_SPARSE})


class BundleHeaderTooLargeError(Exception):
    """A bundle's extended headers exceed :data:`MAX_BUNDLE_EXTENDED_HEADER_BYTES`."""


class _BoundedTarInfo(tarfile.TarInfo):
    """A TarInfo that checks an extended header's size before ``tarfile`` reads it."""

    def _proc_member(self, archive: tarfile.TarFile) -> tarfile.TarInfo:
        """Refuse a header type a bundle never carries, or an extended header past
        the archive's bounds, then process the header as ``tarfile`` would.

        ``_proc_member`` is the hook ``tarfile`` documents for subclasses that handle
        header types differently.
        """
        if self.type in _REFUSED_HEADER_TYPES:
            raise ValueError(f"Unsupported tar header type in bundle: {self.type!r}")
        if isinstance(archive, BundleTarFile):
            if self.type in _EXTENDED_HEADER_TYPES:
                archive.charge_extended_header(size=self.size)
            else:
                archive.consecutive_extended_headers = 0
        # typeshed leaves the hook undeclared, so it is looked up by name.
        process_member = cast(
            Callable[[tarfile.TarFile], tarfile.TarInfo], getattr(super(), "_proc_member")
        )
        return process_member(archive)

    def _proc_gnusparse_10(
        self,
        _following: tarfile.TarInfo,
        _pax_headers: dict[str, str],
        _archive: tarfile.TarFile,
    ) -> None:
        """Refuse a pax-declared GNU sparse map, whose length the archive sets."""
        raise ValueError("Unsupported sparse member in bundle")


class BundleTarFile(tarfile.TarFile):
    """A TarFile for reading an uploaded bundle, with extended headers bounded.

    Open it with ``BundleTarFile.open(fileobj=..., mode="r:gz")``.
    """

    tarinfo = _BoundedTarInfo
    extended_header_bytes: int = 0
    consecutive_extended_headers: int = 0

    def charge_extended_header(self, size: int) -> None:
        """Count one extended header of ``size`` bytes, refusing it past either bound."""
        self.consecutive_extended_headers += 1
        if self.consecutive_extended_headers > MAX_CONSECUTIVE_EXTENDED_HEADERS:
            raise ValueError("Too many extended tar headers in a row before one member")
        self.extended_header_bytes += size
        if self.extended_header_bytes > MAX_BUNDLE_EXTENDED_HEADER_BYTES:
            raise BundleHeaderTooLargeError(
                "This bundle's long file names and extended headers exceed "
                f"{MAX_BUNDLE_EXTENDED_HEADER_BYTES} bytes. A run bundle needs far less."
            )
