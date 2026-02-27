#!/bin/bash

echo "🚀 IXIGO TEST AUTOMATION SYSTEM"
echo "====================================="
echo ""
echo "Starting Frontend + Backend..."
echo ""
echo "✅ Frontend: React + Vite (Port 5173)"
echo "✅ Backend: Flask API (Port 5000)"
echo "✅ Database: SQL Server (Ixigo_TestAutomation)"
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js first."
    exit 1
fi

# Check if Python is installed
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "❌ Python is not installed. Please install Python first."
    exit 1
fi

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm run setup
fi

echo "🎯 Starting the system..."
npm start
