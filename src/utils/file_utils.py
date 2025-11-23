import os
import shutil
import json
from typing import Any, Optional
import logging

logger = logging.getLogger('AutoKaggle')

def ensure_dir(dir_path: str):
    """Create directory if it does not already exist."""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"Created directory: {dir_path}")

def write_json(data: Any, file_path: str):
    """Write JSON data to a file."""
    ensure_dir(os.path.dirname(file_path))
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Successfully wrote JSON to: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write JSON to {file_path}: {e}")

def read_json(file_path: str) -> Optional[Any]:
    """Read JSON data from a file."""
    if not os.path.exists(file_path):
        logger.warning(f"JSON file not found: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.debug(f"Successfully read JSON from: {file_path}")
        return data
    except Exception as e:
        logger.error(f"Failed to read JSON from {file_path}: {e}")
        return None

def write_markdown(content: str, file_path: str):
    """Write Markdown content to a file."""
    ensure_dir(os.path.dirname(file_path))
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.debug(f"Successfully wrote Markdown to: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write Markdown to {file_path}: {e}")

def read_markdown(file_path: str) -> Optional[str]:
    """Read Markdown content from a file."""
    if not os.path.exists(file_path):
        logger.warning(f"Markdown file not found: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"Successfully read Markdown from: {file_path}")
        return content
    except Exception as e:
        logger.error(f"Failed to read Markdown from {file_path}: {e}")
        return None

def copy_file(src: str, dst: str):
    """Copy a file."""
    ensure_dir(os.path.dirname(dst))
    try:
        shutil.copy2(src, dst)  # Copy metadata as well
        logger.debug(f"Copied file from {src} to {dst}")
    except Exception as e:
        logger.error(f"Failed to copy file from {src} to {dst}: {e}")

def move_file(src: str, dst: str):
    """Move a file."""
    ensure_dir(os.path.dirname(dst))
    try:
        shutil.move(src, dst)
        logger.debug(f"Moved file from {src} to {dst}")
    except Exception as e:
        logger.error(f"Failed to move file from {src} to {dst}: {e}")

def remove_dir(dir_path: str):
    """Remove a directory and its contents."""
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Removed directory: {dir_path}")
        except Exception as e:
            logger.error(f"Failed to remove directory {dir_path}: {e}")
