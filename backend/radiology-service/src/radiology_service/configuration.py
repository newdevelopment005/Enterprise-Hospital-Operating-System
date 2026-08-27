from ehos_common.config import ServiceSettings


class RadiologySettings(ServiceSettings):
    service_name: str = "radiology-service"
    service_port: int = 8513
    database_name: str = "ehos_radiology"

    class Config:
        env_prefix = "RADIOLOGY_"


settings = RadiologySettings()
