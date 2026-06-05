#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt --quiet
streamlit run app.py --server.headless true
