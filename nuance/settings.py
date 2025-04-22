from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    # Environment settings
    TESTNET: bool = Field(
        default=False,
        description="Flag to indicate if running in testnet mode.",
    )
    
    # Bittensor
    WALLET_PATH: str = Field(default="~/.bittensor/wallets", description="Path to the Bittensor wallet.")
    WALLET_NAME: str = Field(default="default", description="Name of the Bittensor wallet.")
    WALLET_HOTKEY: str = Field(default="default", description="Hotkey of the Bittensor wallet.")

    # API Keys and Secrets
    DATURA_API_KEY: str = Field(description="Datura API key.")
    NINETEEN_API_KEY: str = Field(default="", description="Nineteen API key.")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )


settings = Settings()
