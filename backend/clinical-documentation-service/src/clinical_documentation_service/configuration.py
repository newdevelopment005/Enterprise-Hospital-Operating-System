from ehos_common.config import ServiceSettings


class ClinicalDocumentationSettings(ServiceSettings):
    service_name: str = "clinical-documentation-service"
    service_port: int = 8516
    database_name: str = "ehos_documentation"

    class Config:
        env_prefix = "CLINICAL_DOC_"


settings = ClinicalDocumentationSettings()
