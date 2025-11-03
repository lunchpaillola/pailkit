"""
Base Transcription Provider - PailKit API

Abstract base class defining the interface for all transcription providers.
This ensures consistent API across different transcription services (Deepgram, AssemblyAI, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any


class TranscriptionProvider(ABC):
    """
    Abstract base class for transcription providers.

    This class defines the standard interface that all transcription providers
    must implement. This allows the PailKit API to work with multiple transcription
    services (Deepgram, AssemblyAI, Daily.co, etc.) through a unified interface.

    **Simple Explanation:**
    Think of this as a "contract" that all transcription providers must follow.
    Just like how different phone brands all have the same basic buttons (call, hang up),
    all transcription providers will have these same methods, but each provider
    implements them differently based on their own API.
    """

    def __init__(self, api_key: str):
        """
        Initialize the transcription provider.

        Args:
            api_key: Provider API key for authentication
        """
        self.api_key = api_key
        self.provider: str = (
            ""  # Will be set by subclasses (e.g., "deepgram", "assemblyai")
        )

    @abstractmethod
    async def start_transcription(
        self,
        audio_url: str | None = None,
        audio_stream: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Start a real-time/streaming transcription.

        This method begins transcribing audio in real-time. It can either:
        - Connect to a live audio stream (for live captions)
        - Process audio from a URL (for room recordings)
        - Process a local audio stream (for direct audio input)

        **Simple Explanation:**
        This is like pressing "record" on a transcription. It starts listening
        and converting speech to text in real-time as people speak.

        Args:
            audio_url: Optional URL to audio source (e.g., room recording URL)
            audio_stream: Optional audio stream object (for direct streaming)
            config: Transcription configuration (from build_config())

        Returns:
            Dictionary with transcription result, including:
            - success: bool - Whether transcription started successfully
            - transcription_id: str - Unique ID for this transcription session
            - provider: str - Provider name (e.g., "deepgram")
            - message: str - Status message
        """
        pass

    @abstractmethod
    async def stop_transcription(self, transcription_id: str) -> dict[str, Any]:
        """
        Stop an active transcription session.

        This method stops a transcription that was started with start_transcription().
        It finalizes any remaining audio and returns the complete transcript.

        **Simple Explanation:**
        This is like pressing "stop" on the transcription recorder. It stops
        listening and gives you the final transcript.

        Args:
            transcription_id: The ID returned from start_transcription()

        Returns:
            Dictionary with stop result, including:
            - success: bool - Whether stop was successful
            - transcription_id: str - The transcription ID
            - final_transcript: str - Complete transcript text
            - provider: str - Provider name
            - message: str - Status message
        """
        pass

    @abstractmethod
    async def submit_batch_job(
        self, audio_url: str, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Submit a batch transcription job for async processing.

        This method uploads an audio file or URL for transcription and processes
        it asynchronously. Use this for:
        - Pre-recorded audio files
        - Room recordings
        - Podcasts or long-form content
        - Files that don't need real-time results

        **Simple Explanation:**
        This is like submitting a document to be typed up. You give them the audio,
        they process it in the background, and you check back later to get the transcript.

        Args:
            audio_url: URL to the audio file to transcribe
            config: Transcription configuration (from build_config())

        Returns:
            Dictionary with job submission result, including:
            - success: bool - Whether job was submitted successfully
            - job_id: str - Unique ID for this transcription job
            - provider: str - Provider name
            - status: str - Job status (e.g., "processing", "queued")
            - message: str - Status message
        """
        pass

    @abstractmethod
    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Get the status and results of a batch transcription job.

        This method checks on a batch job submitted via submit_batch_job().
        It returns the current status and, if complete, the transcript.

        **Simple Explanation:**
        This is like checking the status of your document typing job.
        "Is it done yet? Can I get my transcript?"

        Args:
            job_id: The job ID returned from submit_batch_job()

        Returns:
            Dictionary with job status, including:
            - success: bool - Whether status check was successful
            - job_id: str - The job ID
            - status: str - Current status ("queued", "processing", "completed", "failed")
            - transcript: str | None - Transcript text (if completed)
            - provider: str - Provider name
            - message: str - Status message
        """
        pass
