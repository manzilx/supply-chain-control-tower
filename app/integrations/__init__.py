"""External system integrations (SAP CPI, ERP, etc.).

Each adapter exposes a stable Python interface; the underlying transport
(REST, RFC, SOAP, file) is hidden behind the seam so callers in the rest of
the app don't care which mode is active.
"""
