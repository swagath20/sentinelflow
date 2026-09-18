import base64
from pathlib import Path
from typing import Dict, Any
from PIL import Image

class IngestionPipeline:
    @staticmethod
    def parse_log_file(file_path: str, max_lines: int = 40) -> str:
        """Reads raw logs and extracts the trailing tail lines where failures occur."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        # Focus on the most recent entries
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return "".join(tail).strip()

    @staticmethod
    def encode_image(image_path: str) -> str:
        """Loads and encodes an error screenshot to base64 for vision inspection."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Verify it's a valid readable image
        with Image.open(path) as img:
            img.verify()

        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

if __name__ == "__main__":
    # Self-test: Generate a mock server crash log
    sample_log = "server_crash.log"
    with open(sample_log, "w", encoding="utf-8") as f:
        f.write("INFO 10:00:01 Bootstrapping cluster node-1\n")
        f.write("INFO 10:00:02 Syncing distributed storage metadata\n")
        f.write("CRITICAL 10:00:05 Kernel lock wait timeout exceeded during distributed table synchronization\n")
        f.write("FATAL 10:00:06 Transaction worker 0x8F deadlock state encountered\n")

    parser = IngestionPipeline()
    extracted_error = parser.parse_log_file(sample_log, max_lines=2)
    print("--- Extracted Failure Tail ---")
    print(extracted_error)