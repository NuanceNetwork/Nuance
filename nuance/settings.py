from dotenv import load_dotenv
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    # Environment settings
    TESTNET: bool = Field(
        default=False,
        description="Flag to indicate if running in testnet mode.",
    )
    DEBUG: bool = Field(
        default=False,
        description="Flag to indicate if running in debug mode.",
    )
    
    # Bittensor
    WALLET_PATH: str = Field(default="~/.bittensor/wallets", description="Path to the Bittensor wallet.")
    WALLET_NAME: str = Field(default="default", description="Name of the Bittensor wallet.")
    WALLET_HOTKEY: str = Field(default="default", description="Hotkey of the Bittensor wallet.")

    # API Keys and Secrets
    DATURA_API_KEY: str = Field(description="Datura API key.")
    NINETEEN_API_KEY: str = Field(default="", description="Nineteen API key.")
    
    # Database settings
    DATABASE_URL: PostgresDsn = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/nuance",
        description="Database connection URL (PostgreSQL with asyncpg driver)"
    )
    DATABASE_POOL_SIZE: int = Field(
        default=5,
        description="Maximum size of the database connection pool."
    )
    DATABASE_MAX_OVERFLOW: int = Field(
        default=10,
        description="Maximum overflow of connections beyond pool_size."
    )
    DATABASE_POOL_TIMEOUT: int = Field(
        default=30,
        description="Number of seconds to wait before giving up on getting a connection from the pool."
    )
    DATABASE_ECHO: bool = Field(
        default=False,
        description="Echo SQL statements to stdout (defaults to debug setting if None)."
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )
    
    @property
    def database_engine_kwargs(self) -> dict:
        """Get SQLAlchemy engine kwargs from settings."""
        echo = self.DATABASE_ECHO if self.DATABASE_ECHO else self.DEBUG
        return {
            "echo": echo,
            "pool_size": self.DATABASE_POOL_SIZE,
            "max_overflow": self.DATABASE_MAX_OVERFLOW,
            "pool_timeout": self.DATABASE_POOL_TIMEOUT
        }
        
    @property
    def database_url(self) -> str:
        """Get the database URL from settings."""
        return str(self.DATABASE_URL)


settings = Settings()
