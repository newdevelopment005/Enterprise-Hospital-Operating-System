from ehos_common.config import ServiceSettings


class LaboratorySettings(ServiceSettings):
    service_name: str = "laboratory-service"
    service_port: int = 8512
    database_name: str = "ehos_laboratory"

    class Config:
        env_prefix = "LABORATORY_"


settings = LaboratorySettings()
