"""YouTube Transcript Chunker"""

import tiktoken
from typing import Optional
import config

def estimate_tokens(text: str, model: str = "meta-llama/llama-3.3-70b-instruct") -> int:
    """Estimate token count for text."""
    try:
        if "claude" in model.lower() or "gpt" in model.lower():
            enc = tiktoken.get_encoding("cl100k_base")
        else:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except:
        return len(text) // 4

def format_timestamp(seconds: float) -> str:
    """Format seconds to MM:SS or HH:MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def create_text_from_transcript(transcript: list[dict]) -> str:
    """Convert transcript list to plain text with timestamps."""
    lines = []
    for entry in transcript:
        timestamp = format_timestamp(entry['start'])
        text = entry['text']
        lines.append(f"[{timestamp}] {text}")
    return "\n".join(lines)

def chunk_transcript(
    transcript: list[dict],
    max_tokens: int = None,
    overlap_tokens: int = None,
    model: str = None
) -> list[dict]:
    """
    Chunk transcript into smaller pieces for LLM processing.
    
    Args:
        transcript: List of transcript entries [{text, start, duration}]
        max_tokens: Maximum tokens per chunk (configurable)
        overlap_tokens: Overlap between chunks (10% of max_tokens)
        model: Model name for token estimation
    
    Returns:
        List of chunks: [{
            'text': str,
            'start': float,
            'end': float,
            'tokens': int
        }]
    """
    model = model or config.DEFAULT_MODEL
    max_tokens = max_tokens or config.CHUNK_SIZE_TOKENS
    overlap_tokens = overlap_tokens or config.CHUNK_OVERLAP_TOKENS
    
    if not transcript:
        return []
    
    # Convert to text with timestamps
    full_text = create_text_from_transcript(transcript)
    
    # Estimate total tokens
    total_tokens = estimate_tokens(full_text, model)
    
    # If within limits, return single chunk
    if total_tokens <= max_tokens:
        return [{
            'text': full_text,
            'start': transcript[0]['start'],
            'end': transcript[-1]['start'] + transcript[-1].get('duration', 0),
            'tokens': total_tokens
        }]
    
    # Chunk with overlap
    chunks = []
    current_pos = 0
    chunk_start_time = 0
    
    while current_pos < len(transcript):
        chunk_entries = []
        chunk_tokens = 0
        chunk_start = transcript[current_pos]['start']
        
        # Build chunk
        for i in range(current_pos, len(transcript)):
            entry = transcript[i]
            entry_text = f"[{format_timestamp(entry['start'])}] {entry['text']}"
            entry_tokens = estimate_tokens(entry_text, model)
            
            if chunk_tokens + entry_tokens > max_tokens and chunk_entries:
                break
            
            chunk_entries.append(entry)
            chunk_tokens += entry_tokens
        
        # Compute end time
        last_entry = chunk_entries[-1]
        chunk_end = last_entry['start'] + last_entry.get('duration', 0)
        
        chunks.append({
            'text': create_text_from_transcript(chunk_entries),
            'start': chunk_start,
            'end': chunk_end,
            'tokens': chunk_tokens
        })
        
        # Move to next chunk with overlap
        overlap_count = max(1, len(chunk_entries) // 10)
        next_start = min(current_pos + len(chunk_entries) - overlap_count, len(transcript) - 1)
        
        if next_start <= current_pos:
            next_start = current_pos + 1
            
        current_pos = next_start
    
    return chunks

def get_chunk_count_info(chunks: list[dict]) -> str:
    """Get info string about chunks."""
    if len(chunks) == 1:
        return f"1 chunk (~{chunks[0]['tokens']} tokens)"
    return f"{len(chunks)} chunks (~{sum(c['tokens'] for c in chunks)} tokens total)"