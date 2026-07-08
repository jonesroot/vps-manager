from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Server:
    alias: str
    host: str
    user: str
    port: int
    auth_type: str = "key"
    password: Optional[str] = None
    key_path: Optional[str] = None
    description: Optional[str] = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Server':
        return cls(
            alias=data["alias"],
            host=data["host"],
            user=data["user"],
            port=int(data["port"]),
            auth_type=data.get("auth_type", "key"),
            password=data.get("password"),
            key_path=data.get("key_path"),
            description=data.get("description", "")
        )