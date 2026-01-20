from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
from utils.logger import get_logger
from core.memory_store import MemoryStore

logger = get_logger(__name__)


@dataclass
class Intent:
    """Structured intent from user input"""
    action: str  # 'organize', 'move', 'delete', 'search', etc.
    target: Optional[str] = None  # What to act on
    destination: Optional[str] = None
    strategy: Optional[str] = None
    filters: Optional[Dict] = None
    confidence: float = 1.0
    original_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "destination": self.destination,
            "strategy": self.strategy,
            "filters": self.filters,
            "confidence": self.confidence
        }


class IntentProcessor:
    """
    Natural language understanding for file operations
    """
    
    def __init__(self, memory: Optional[MemoryStore] = None):
        self.logger = logger.bind(component="IntentProcessor")
        self.memory = memory or MemoryStore()
        
        # Action keywords mapping
        self.action_keywords = {
            "organize": ["organize", "sort", "arrange", "clean up", "tidy"],
            "move": ["move", "transfer", "relocate", "put"],
            "copy": ["copy", "duplicate", "clone"],
            "delete": ["delete", "remove", "trash", "get rid of"],
            "search": ["find", "search", "look for", "locate"],
            "create": ["create", "make", "new"],
            "rename": ["rename", "change name"],
            "scan": ["show", "list", "what's in", "see"],
        }
        
        # Strategy keywords
        self.strategy_keywords = {
            "by_file_type": ["by type", "by file type", "by extension"],
            "by_date": ["by date", "by time", "by age", "chronologically"],
            "by_size": ["by size", "by file size"],
        }
    
    async def parse_intent(self, user_input: str) -> Intent:
        """
        Parse natural language input into structured intent
        
        Args:
            user_input: What user said
            
        Returns:
            Structured Intent object
        """
        text = user_input.lower().strip()
        
        self.logger.info("parsing_intent", input=user_input)
        
        # Extract action
        action = self._extract_action(text)
        
        # Extract target (folder/file)
        target = self._extract_target(text)
        
        # Extract destination (for move/copy)
        destination = self._extract_destination(text)
        
        # Extract strategy (for organize)
        strategy = self._extract_strategy(text)
        
        # Extract filters
        filters = self._extract_filters(text)
        
        # Calculate confidence
        confidence = self._calculate_confidence(text, action, target)
        
        intent = Intent(
            action=action,
            target=target,
            destination=destination,
            strategy=strategy,
            filters=filters,
            confidence=confidence,
            original_text=user_input
        )
        
        self.logger.info("intent_parsed", intent=intent.to_dict())
        
        return intent
    
    def _extract_action(self, text: str) -> str:
        """Extract primary action from text"""
        for action, keywords in self.action_keywords.items():
            if any(keyword in text for keyword in keywords):
                return action
        
        # Default action based on context
        if "?" in text or text.startswith(("what", "show", "list")):
            return "scan"
        
        return "unknown"
    
    def _extract_target(self, text: str) -> Optional[str]:
        """Extract target folder/file from text"""
        # Common folder references
        folders = ["downloads", "desktop", "documents", "folder"]
        
        for folder in folders:
            if folder in text:
                # Try to get the actual path
                if "my" in text or "the" in text:
                    return folder
                return folder
        
        # Check for file extensions
        import re
        ext_match = re.search(r'\.(pdf|jpg|png|txt|doc|csv|zip|mp4)', text)
        if ext_match:
            return f"*.{ext_match.group(1)}"
        
        # Extract quoted strings
        quote_match = re.search(r'"([^"]+)"', text) or re.search(r"'([^']+)'", text)
        if quote_match:
            return quote_match.group(1)
        
        return None
    
    def _extract_destination(self, text: str) -> Optional[str]:
        """Extract destination from text"""
        # Look for "to X" or "into X"
        import re
        
        # Pattern: "to/into <destination>"
        to_match = re.search(r'\b(?:to|into)\s+(?:my\s+)?(\w+)', text)
        if to_match:
            return to_match.group(1)
        
        return None
    
    def _extract_strategy(self, text: str) -> Optional[str]:
        """Extract organization strategy from text"""
        for strategy, keywords in self.strategy_keywords.items():
            if any(keyword in text for keyword in keywords):
                return strategy
        
        # Default strategy based on memory
        return None
    
    def _extract_filters(self, text: str) -> Optional[Dict]:
        """Extract filters from text"""
        filters = {}
        
        # Size filters
        if "large" in text or "big" in text:
            filters["min_size_mb"] = 10
        if "small" in text:
            filters["max_size_mb"] = 1
        
        # Time filters
        if "recent" in text or "new" in text:
            filters["max_age_days"] = 7
        if "old" in text:
            filters["min_age_days"] = 30
        
        # Type filters
        import re
        type_match = re.search(r'(pdf|image|video|document|code)s?', text)
        if type_match:
            filters["category"] = type_match.group(1).title() + "s"
        
        return filters if filters else None
    
    def _calculate_confidence(
        self,
        text: str,
        action: str,
        target: Optional[str]
    ) -> float:
        """Calculate confidence score for intent"""
        score = 0.5  # Base confidence
        
        # Boost if action is clear
        if action != "unknown":
            score += 0.3
        
        # Boost if target is specified
        if target:
            score += 0.2
        
        # Penalize if text is very short or vague
        if len(text.split()) < 3:
            score -= 0.2
        
        # Boost if text has clear structure
        if any(word in text for word in ["my", "the", "all"]):
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    async def suggest_intent_completion(
        self,
        partial_intent: Intent
    ) -> Intent:
        """
        Use memory to complete partial intents
        
        Example: User says "organize downloads"
        Memory knows they usually organize by type
        Returns: Intent with strategy="by_file_type"
        """
        if not partial_intent.target:
            return partial_intent
        
        # Get folder preference from memory
        folder_pref = await self.memory.get_folder_preference(partial_intent.target)
        
        if folder_pref and not partial_intent.strategy:
            # Use last strategy if available
            if folder_pref.last_strategy:
                partial_intent.strategy = folder_pref.last_strategy
                partial_intent.confidence += 0.1
                
                self.logger.info(
                    "intent_completed_from_memory",
                    strategy=folder_pref.last_strategy
                )
        
        return partial_intent
    
    async def learn_from_execution(
        self,
        intent: Intent,
        success: bool
    ):
        """Learn from executed intents to improve future parsing"""
        if success and intent.target:
            # Record successful pattern
            await self.memory.record_folder_access(
                folder_path=intent.target,
                strategy=intent.strategy
            )
            
            self.logger.info(
                "learned_from_execution",
                action=intent.action,
                target=intent.target
            )