from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Package:
    id: str
    name: str
    version: str
    uploaded_by: str
    upload_timestamp: datetime
    size_bytes: int
    metadata: Dict[str, Any]
    s3_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'uploaded_by': self.uploaded_by,
            'upload_timestamp': self.upload_timestamp.isoformat(),
            'size_bytes': self.size_bytes,
            'metadata': self.metadata,
            's3_key': self.s3_key
        }
