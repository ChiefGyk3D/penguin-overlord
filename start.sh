#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Quick start script for Penguin Overlord bot

set -e

echo "🐧 Penguin Overlord - Quick Start"
echo "=================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

echo "✅ Python $(python3 --version) found"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment exists"
fi

echo ""
echo "🔧 Activating virtual environment..."
source venv/bin/activate

echo "✅ Virtual environment activated"
echo ""

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"
echo ""

# Check for .env or Doppler
if [ -f ".env" ]; then
    echo "✅ .env file found"
elif [ ! -z "$DOPPLER_TOKEN" ]; then
    echo "✅ DOPPLER_TOKEN is set"
else
    echo "⚠️  No .env file or DOPPLER_TOKEN found"
    echo ""
    echo "Please configure your secrets:"
    echo "  1. Copy .env.example to .env and add your Discord bot token"
    echo "     cp .env.example .env"
    echo "  2. OR set up Doppler (see DOPPLER_SETUP.md)"
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to exit..."
fi

echo ""
echo "🧪 Testing configuration..."
if python scripts/feed-check/test_secrets.py; then
    echo ""
    echo "=================================="
    echo "🚀 Starting Penguin Overlord bot..."
    echo "=================================="
    echo ""
    
    cd penguin-overlord
    python bot.py
else
    echo ""
    echo "❌ Configuration test failed!"
    echo "Please fix the errors above before starting the bot."
    exit 1
fi
