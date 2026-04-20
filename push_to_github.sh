#!/bin/bash
# Push Game Surf LLM WSL project to GitHub
# Usage: ./push_to_github.sh <GITHUB_REPO_URL>
# Example: ./push_to_github.sh https://github.com/username/game-surf-llm-wsl.git

if [ -z "$1" ]; then
    echo "Error: GitHub repository URL required"
    echo "Usage: $0 <GITHUB_REPO_URL>"
    echo "Example: $0 https://github.com/username/game-surf-llm-wsl.git"
    exit 1
fi

REPO_URL="$1"

echo "Setting up GitHub remote..."
git remote add origin "$REPO_URL"

echo "Renaming branch to main..."
git branch -M main

echo "Pushing to GitHub..."
git push -u origin main

echo "✓ Successfully pushed to $REPO_URL"
echo "Repository is now available at: $REPO_URL"
