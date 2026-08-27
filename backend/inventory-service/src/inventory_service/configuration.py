from ehos_common.config import ServiceSettings


class InventorySettings(ServiceSettings):
    service_name: str = "inventory-service"
    service_port: int = 8514
    database_name: str = "ehos_inventory"

    class Config:
        env_prefix = "INVENTORY_"


settings = InventorySettings()
