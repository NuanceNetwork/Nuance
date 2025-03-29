
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
    
    # API Keys and Secrets
    DATURA_API_KEY: str = Field(description="Datura API key.")
    CHUTES_API_KEY: str = Field(description="Chutes API key.")
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
