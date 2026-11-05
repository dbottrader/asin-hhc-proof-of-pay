"""ASIN-HHC Proof of Pay — registration.

Gives a Hermes agent the ASIN-HHC third-party verification layer:
evidence-receipt validation, provenance-index chain verification, and the
live work-market board — all over ASIN-HHC's published public artifacts.
Read-only: the plugin makes GET requests to the public artifacts host and
never writes, posts, or transacts.
"""

import logging

try:
    from . import pop_client, schemas, tools
except ImportError:  # direct module context (tests, tooling)
    import pop_client, schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire schemas to handlers."""
    try:
        base_url = ctx.get_config("base_url", default=pop_client.DEFAULT_BASE_URL)
    except Exception:
        base_url = pop_client.DEFAULT_BASE_URL
    pop_client.configure(base_url)

    ctx.register_tool(
        name="asin_hhc_verify_receipt",
        toolset="asin_hhc",
        schema=schemas.VERIFY_RECEIPT,
        handler=tools.verify_receipt,
    )
    ctx.register_tool(
        name="asin_hhc_check_provenance",
        toolset="asin_hhc",
        schema=schemas.CHECK_PROVENANCE,
        handler=tools.check_provenance,
    )
    ctx.register_tool(
        name="asin_hhc_board",
        toolset="asin_hhc",
        schema=schemas.BOARD,
        handler=tools.board,
    )
    logger.info("asin-hhc-proof-of-pay: 3 tools registered (base %s)", pop_client.base_url())
