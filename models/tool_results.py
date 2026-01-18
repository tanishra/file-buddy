from typing import Dict, List, Optional, Union
from dataclasses import dataclass, asdict

@dataclass
class ToolResult:
    """Standard tool result"""
    success: bool
    data: Optional[Union[Dict, List, str, int, float, bool]] = None
    message: Optional[str] = None
    error: Optional[str] = None
    snapshot_id: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dictionary"""
        def sanitize(value):
            if isinstance(value, dict):
                return {k: sanitize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitize(v) for v in value]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)  # fallback safety

        raw = asdict(self)
        return {k: sanitize(v) for k, v in raw.items() if v is not None}
