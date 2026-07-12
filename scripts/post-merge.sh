#!/bin/bash
set -e

# Install Python dependencies (idempotent — pip skips already-satisfied packages)
pip install -r requirements.txt
