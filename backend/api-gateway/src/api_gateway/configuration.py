from ehos_common.config import ServiceSettings
from ehos_common.config import get_settings as _get_settings


def get_settings() -> ServiceSettings:
    return _get_settings(service_name="api-gateway", database_name="ehos_gateway")