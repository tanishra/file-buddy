import random
from datetime import datetime

# Time-based greetings
def _get_time_greeting() -> str:
    """Get greeting based on time of day"""
    hour = datetime.now().hour
    
    if hour < 12:
        return "Good morning! I'm Friday, your File Organizer AI."
    elif hour < 18:
        return "Good afternoon! I'm Friday, your File Organizer AI."
    else:
        return "Good evening! I'm Friday, your File Organizer AI."

# Seasonal greetings
def _get_seasonal_greeting() -> str:
    """Get greeting based on season"""
    month = datetime.now().month
    
    # Spring (Mar-May)
    if 3 <= month <= 5:
        return "Hi! I'm Friday, your File Organizer AI. Spring cleaning time!"
    # Summer (Jun-Aug)
    elif 6 <= month <= 8:
        return "Hey! I'm Friday, your File Organizer AI. Let's organize while it's sunny!"
    # Fall (Sep-Nov)
    elif 9 <= month <= 11:
        return "Hello! I'm Friday, your File Organizer AI. Fall cleanup ready!"
    # Winter (Dec-Feb)
    else:
        return "Hi! I'm Friday, your File Organizer AI. Cozy organizing time!"

# Standard greeting
INITIAL_GREETING = """Hi! I'm Friday, your File Organizer AI.

I can help you organize, search, create, and manage files safely. Which folder should we start with?"""

# Alternative greetings
ALTERNATIVE_GREETINGS = [
    "Hey! I'm Friday. Ready to organize some files? Which folder needs attention?",
    "Hello! Friday here. I'll help you keep your files organized. Want to start with Downloads or Desktop?",
    "Hi there! I'm Friday, your file assistant. Tell me which folder you'd like to organize!",
]

# Post-operation greetings
READY_FOR_MORE = "What else can I help you organize?"
OPERATION_COMPLETE = "All done! Anything else you need?"

# Help message
HELP_MESSAGE = """I can:
• Scan and organize folders
• Search for files
• Create files and folders
• Move, copy, or rename files
• Safely delete files (with confirmation)
• Undo recent operations

Just tell me what you need!"""

# Confirmation prompts
CONFIRMATION_PROMPTS = {
    "organize": "Ready to organize {count} files into {folders} folders?",
    "delete": "Delete {count} files? Say 'confirm delete' to proceed.",
    "move": "Move {count} files to {destination}?",
    "copy": "Copy {count} files to {destination}?",
}

# Success messages
SUCCESS_MESSAGES = {
    "organize": "Organized {count} files! Say 'undo' to revert.",
    "delete": "Deleted {count} files (moved to trash).",
    "move": "Moved {count} files to {destination}.",
    "copy": "Copied {count} files.",
    "create": "Created {name}.",
    "undo": "Undone! Restored everything.",
}

# Error messages
ERROR_MESSAGES = {
    "permission_denied": "I don't have permission to access that folder. Try Downloads or Desktop?",
    "not_found": "I couldn't find that folder. Can you double-check the path?",
    "invalid_operation": "I can't do that safely. Try something else?",
    "system_folder": "That's a system folder - I can't touch those for safety!",
}


def get_greeting(style: str = "default") -> str:
    """
    Get a greeting message
    
    Args:
        style: 'default', 'time', 'seasonal', 'alternative', 'help', 'ready'
    
    Returns:
        Greeting string
    """
    if style == "default":
        return INITIAL_GREETING
    elif style == "time":
        time_greeting = _get_time_greeting()
        return f"{time_greeting}\n\nI can help you organize, search, create, and manage files safely. Which folder should we start with?"
    elif style == "seasonal":
        seasonal_greeting = _get_seasonal_greeting()
        return f"{seasonal_greeting}\n\nI can help you organize, search, create, and manage files safely. Which folder should we start with?"
    elif style == "alternative":
        return random.choice(ALTERNATIVE_GREETINGS)
    elif style == "help":
        return HELP_MESSAGE
    elif style == "ready":
        return READY_FOR_MORE
    else:
        return INITIAL_GREETING


def get_confirmation_message(operation: str, **kwargs) -> str:
    """Get confirmation message for operation"""
    template = CONFIRMATION_PROMPTS.get(operation, "Proceed with {operation}?")
    try:
        return template.format(**kwargs)
    except KeyError:
        return f"Proceed with {operation}?"


def get_success_message(operation: str, **kwargs) -> str:
    """Get success message for operation"""
    template = SUCCESS_MESSAGES.get(operation, "Done!")
    try:
        return template.format(**kwargs)
    except KeyError:
        return "Done!"


def get_error_message(error_type: str) -> str:
    """Get user-friendly error message"""
    return ERROR_MESSAGES.get(
        error_type,
        "Something went wrong. Let's try something else?"
    )