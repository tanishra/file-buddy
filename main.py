import logging
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    Agent,
    room_io,
    ChatContext,
    BackgroundAudioPlayer, 
    AudioConfig, 
    BuiltinAudioClip,
)
from livekit.plugins import openai, noise_cancellation, deepgram, silero

# Core components
from core.confirmation import ConfirmationManager
from config.prompts import SYSTEM_PROMPT
from config.greetings import get_greeting
from utils.logger import get_logger
from config.settings import Settings

# Tools
from tools.read_tools import (
    scan_folder_tool,
    search_files_tool, # To be tested
    get_file_info_tool,
    read_file_content_tool,
    preview_file_tool,
    read_folder_tree_tool,
    search_file_contents_tool,
    detect_project_type_tool
)
from tools.create_tools import (
    create_file_tool,
    create_folder_tool,
    create_any_files_tool,
    create_project_structure_tool
)
from tools.mutate_tools import (
    move_files_tool,
    copy_files_tool,
    rename_file_tool,
    batch_rename_tool,
    batch_rename_tool,
    move_folder_contents_tool,
    copy_folder_contents_tool
)
from tools.organize_tools import (
    organize_folder_tool,
    execute_organize,
    organize_by_size_tool,
    organize_by_size_tool,
    organize_by_extension_tool,
    normalize_filenames_tool,
    flatten_folder_tool
)
from tools.dangerous_tools import (
    delete_files_tool,
    execute_delete,
    delete_folder_tool,
    delete_multiple_folders_tool,
    delete_multiple_folders_tool,
    delete_mixed_items_tool,
    conditional_delete_preview_tool
)
from tools.utility_tools import (
    undo_last_action_tool,
    show_history_tool,
    clear_undo_state_tool,
    peek_last_action_tool,
    system_state_tool,
    redo_last_action_tool,
    undo_to_snapshot_tool,
    list_available_snapshots_tool,
    list_available_snapshots_tool,
    begin_transaction_tool,
    end_transaction_tool
)

load_dotenv(".env.local")

logger = get_logger(__name__)

# All active tools
tools = [
    scan_folder_tool,
    search_files_tool,
    get_file_info_tool,
    detect_project_type_tool,
    create_file_tool,
    create_folder_tool,
    move_files_tool,
    copy_files_tool,
    rename_file_tool,
    organize_folder_tool,
    execute_organize,
    delete_files_tool,
    execute_delete,
    delete_folder_tool,
    undo_last_action_tool,
    show_history_tool,
    create_any_files_tool,
    create_project_structure_tool,
    read_file_content_tool,
    preview_file_tool,
    read_folder_tree_tool,
    search_file_contents_tool,
    batch_rename_tool,
    move_folder_contents_tool,
    copy_folder_contents_tool,
    organize_by_size_tool,
    organize_by_extension_tool,
    normalize_filenames_tool,
    flatten_folder_tool,
    delete_multiple_folders_tool,
    delete_mixed_items_tool,
    conditional_delete_preview_tool,
    clear_undo_state_tool,
    peek_last_action_tool,
    system_state_tool,
    redo_last_action_tool,
    undo_to_snapshot_tool,
    list_available_snapshots_tool,
    begin_transaction_tool,
    end_transaction_tool
]


class FileBuddy(Agent):
    """
    File Organizer AI Assistant with full tool integration
    """

    def __init__(self, chat_ctx=None) -> None:
        logger.info("Initializing FileBuddy")
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=tools,
            stt=deepgram.STT(model=Settings.DEEPGRAM_STT),
            llm=openai.LLM(model=Settings.OPENAI_MODEL),
            tts=deepgram.TTS(model=Settings.DEEPGRAM_TTS),
            vad=silero.VAD.load(),
            chat_ctx=chat_ctx,
        )

        self.confirmation_mgr = ConfirmationManager()
        self.awaiting_confirmation = False
        self.pending_tool_call_id = None

        logger.info("FileBuddy initialized successfully")


server = AgentServer()


@server.rtc_session()
async def file_organizer_agent(ctx: agents.JobContext):
    logger.info("RTC session started", room=ctx.room.name)

    session = AgentSession()
    chat_ctx = ChatContext()

    assistant = FileBuddy(chat_ctx=chat_ctx)

    try:
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        noise_cancellation.BVCTelephony()
                        if params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                        else noise_cancellation.BVC()
                    ),
                ),
            ),
        )

        logger.info("Agent session started successfully")

        background_audio = BackgroundAudioPlayer(
            thinking_sound=[
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING,volume=1),
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2,volume=1)
                ]
            )
        
        await background_audio.start(room=ctx.room,agent_session=session)

        await session.generate_reply(instructions=f"Say this greeting exactly: {get_greeting('seasonal')}")

        logger.info("Initial greeting delivered")

    except Exception as e:
        logger.exception("Fatal error in File Organizer session", exc_info=e)
        raise


if __name__ == "__main__":
    logger.info("🚀 Starting File Buddy Server")
    logger.info("📁 File tools loaded")
    logger.info("🔒 Safety checks active")
    logger.info("📝 Logging enabled")

    agents.cli.run_app(server)