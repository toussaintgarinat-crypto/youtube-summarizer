"""
YouTube Summarizer - CLI Interface
"""

import sys
import argparse
from src import extractor, chunker, analyzer, fusion

def main():
    parser = argparse.ArgumentParser(description="YouTube Summarizer CLI")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--model", "-m", default=None, help="LLM model to use")
    parser.add_argument("--chunk-size", "-c", type=int, default=None, help="Max tokens per chunk")
    parser.add_argument("--output", "-o", help="Output file path")
    
    args = parser.parse_args()
    
    print(f"📥 Extraction transcript...")
    result = extractor.get_transcript(args.url)
    transcript = result['transcript']
    video_title = result.get('title', f"Video {result['video_id']}")
    
    print(f"✂️ Découpage en chunks...")
    chunks = chunker.chunk_transcript(transcript, max_tokens=args.chunk_size)
    
    print(f"🤖 Analyse de {len(chunks)} chunk(s)...")
    analyses = []
    for i, chunk in enumerate(chunks):
        print(f"  → Chunk {i+1}/{len(chunks)}")
        analysis = analyzer.analyze_chunk(chunk['text'], video_title, model=args.model)
        analyses.append(analysis)
    
    if len(analyses) > 1:
        print(f"🔗 Fusion des analyses...")
        final_report = fusion.fusion_analyses(analyses, video_title, args.model)
    else:
        final_report = analyses[0]
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(final_report)
        print(f"💾 Sauvegardé dans {args.output}")
    else:
        print("\n" + "="*50)
        print(final_report)

if __name__ == "__main__":
    main()