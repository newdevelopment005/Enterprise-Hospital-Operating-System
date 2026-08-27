from ehos_common.config import ServiceSettings


class ReportingSettings(ServiceSettings):
    service_name: str = "reporting-service"
    service_port: int = 8518
    database_name: str = "ehos_reporting"

    class Config:
        env_prefix = "REPORTING_"


settings = ReportingSettings()
