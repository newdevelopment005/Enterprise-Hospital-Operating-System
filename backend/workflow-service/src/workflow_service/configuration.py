from ehos_common.config import ServiceSettings


class WorkflowSettings(ServiceSettings):
    service_name: str = "workflow-service"
    service_port: int = 8515
    database_name: str = "ehos_workflow"

    class Config:
        env_prefix = "WORKFLOW_"


settings = WorkflowSettings()
