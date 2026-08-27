from ehos_common.config import ServiceSettings


class InsuranceSettings(ServiceSettings):
    service_name: str = "insurance-service"
    service_port: int = 8517
    database_name: str = "ehos_insurance"

    class Config:
        env_prefix = "INSURANCE_"


settings = InsuranceSettings()
