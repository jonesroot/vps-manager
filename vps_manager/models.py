import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

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
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Server':
        return cls(
            alias=data["alias"],
            host=data["host"],
            user=data["user"],
            port=int(data["port"]),
            auth_type=data.get("auth_type", "key"),
            password=data.get("password"),
            key_path=data.get("key_path"),
            description=data.get("description", ""),
            tags=data.get("tags") or []
        )

    def validate(self) -> Optional[str]:
        """Memverifikasi seluruh parameter server sebelum disimpan ke media penyimpanan."""
        if not self.alias or not re.match(r"^[a-zA-Z0-9_\-]+$", self.alias):
            return "Alias hanya diperbolehkan berisi karakter alfanumerik, dash (-), dan underscore (_)."
        if not self.host:
            return "Alamat Host atau IP server tujuan wajib diisi."
        if not self.user:
            return "Nama pengguna SSH (SSH Username) wajib ditentukan."
        if not (1 <= self.port <= 65535):
            return "Port komunikasi SSH harus berada di rentang angka 1 s.d. 65535."
        if self.auth_type == "password" and not self.password:
            return "Kata sandi wajib dicantumkan jika menggunakan autentikasi Password."
        if self.auth_type == "key" and not self.key_path:
            return "Lokasi file Private Key wajib dicantumkan jika menggunakan autentikasi Kunci SSH."
        return None


@dataclass
class Snippet:
    name: str
    command: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Snippet':
        return cls(
            name=data["name"],
            command=data["command"],
            description=data.get("description", "")
        )
