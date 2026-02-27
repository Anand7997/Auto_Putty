#!/bin/bash

# Linux Chrome Installation Script for Selenium Automation
# This script installs Google Chrome and all required dependencies for headless automation

set -e  # Exit on any error

echo "🚀 Installing Google Chrome and dependencies for Selenium automation on Linux..."

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo $ID
    elif [ -f /etc/redhat-release ]; then
        if grep -q "CentOS" /etc/redhat-release; then
            echo "centos"
        else
            echo "rhel"
        fi
    else
        echo "unknown"
    fi
}

# Install system dependencies
install_system_dependencies() {
    local distro=$(detect_distro)
    print_status "Detected distribution: $distro"
    
    case $distro in
        ubuntu|debian)
            print_status "Installing system dependencies for Ubuntu/Debian..."
            sudo apt-get update
            sudo apt-get install -y \
                wget \
                gnupg \
                ca-certificates \
                fonts-liberation \
                libasound2 \
                libatk-bridge2.0-0 \
                libatk1.0-0 \
                libatspi2.0-0 \
                libcups2 \
                libdbus-1-3 \
                libdrm2 \
                libgbm1 \
                libgtk-3-0 \
                libnspr4 \
                libnss3 \
                libxcomposite1 \
                libxdamage1 \
                libxfixes3 \
                libxrandr2 \
                xdg-utils \
                libu2f-udev \
                libvulkan1 \
                libxshmfence1 \
                libxtst6 \
                xvfb
            ;;
        centos|rhel|fedora)
            print_status "Installing system dependencies for CentOS/RHEL/Fedora..."
            sudo yum install -y \
                wget \
                gnupg \
                ca-certificates \
                cups-libs \
                dbus-glib \
                GConf2 \
                gtk3 \
                libXcomposite \
                libXcursor \
                libXdamage \
                libXext \
                libXi \
                libXrandr \
                libXScrnSaver \
                libXtst \
                pango \
                xorg-x11-fonts-Type1 \
                xorg-x11-utils \
                vulkan
            ;;
        *)
            print_warning "Unknown distribution. Installing basic dependencies..."
            sudo yum install -y wget gnupg ca-certificates || sudo apt-get install -y wget gnupg ca-certificates
            ;;
    esac
}

# Install Google Chrome
install_chrome() {
    local distro=$(detect_distro)
    
    print_status "Installing Google Chrome..."
    
    case $distro in
        ubuntu|debian)
            # Add Google Chrome repository
            wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
            echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
            sudo apt-get update
            sudo apt-get install -y google-chrome-stable
            ;;
        centos|rhel|fedora)
            # Download and install Chrome RPM package
            wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm -O chrome.rpm
            sudo rpm -ivh chrome.rpm
            sudo yum install -y google-chrome-stable
            rm -f chrome.rpm
            ;;
        *)
            print_error "Unsupported distribution. Please install Chrome manually."
            exit 1
            ;;
    esac
    
    print_status "Google Chrome installed successfully!"
}

# Install ChromeDriver
install_chromedriver() {
    print_status "Installing ChromeDriver..."
    
    # Get Chrome version
    local chrome_version=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+')
    print_status "Detected Chrome version: $chrome_version"
    
    # Get major version
    local major_version=$(echo $chrome_version | cut -d. -f1)
    
    # Download matching ChromeDriver version
    local driver_url="https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${major_version}"
    local driver_version=$(curl -s $driver_url)
    
    if [ -z "$driver_version" ]; then
        print_warning "Could not determine ChromeDriver version. Using latest stable version."
        driver_version=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE")
    fi
    
    print_status "Using ChromeDriver version: $driver_version"
    
    # Download ChromeDriver
    local driver_file="chromedriver_linux64.zip"
    wget "https://chromedriver.storage.googleapis.com/${driver_version}/chromedriver_linux64.zip" -O $driver_file
    
    # Extract and install
    unzip $driver_file
    sudo mv chromedriver /usr/local/bin/
    sudo chmod +x /usr/local/bin/chromedriver
    rm $driver_file
    
    print_status "ChromeDriver installed successfully!"
}

# Install Python dependencies
install_python_dependencies() {
    print_status "Installing Python dependencies..."
    
    pip3 install --user --upgrade \
        selenium \
        webdriver-manager \
        psutil \
        pyautogui \
        pillow
}

# Setup virtual display (optional)
setup_virtual_display() {
    print_status "Setting up virtual display..."
    
    # Check if X server is running
    if ! pgrep -f "Xvfb" > /dev/null; then
        print_status "Starting Xvfb on display :99..."
        Xvfb :99 -screen 0 1920x1080x24 &
        export DISPLAY=:99
        echo "export DISPLAY=:99" >> ~/.bashrc
        print_status "Virtual display configured"
    else
        print_status "Xvfb is already running"
    fi
}

# Create Chrome and ChromeDriver symlinks
create_symlinks() {
    print_status "Creating symlinks..."
    
    # Find Chrome binary
    local chrome_bin=$(which google-chrome || find /usr -name "chrome" -type f 2>/dev/null | head -1)
    
    if [ -n "$chrome_bin" ]; then
        sudo ln -sf $chrome_bin /usr/local/bin/chrome
        print_status "Created Chrome symlink: /usr/local/bin/chrome -> $chrome_bin"
    fi
    
    # Ensure ChromeDriver is accessible
    if [ -f "/usr/local/bin/chromedriver" ]; then
        sudo ln -sf /usr/local/bin/chromedriver /usr/local/bin/chromedriver
        print_status "ChromeDriver symlink verified"
    fi
}

# Test installation
test_installation() {
    print_status "Testing Chrome installation..."
    
    # Test Chrome
    if google-chrome --version > /dev/null 2>&1; then
        print_status "✅ Chrome installation successful"
    else
        print_error "❌ Chrome installation failed"
        return 1
    fi
    
    # Test ChromeDriver
    if chromedriver --version > /dev/null 2>&1; then
        print_status "✅ ChromeDriver installation successful"
    else
        print_error "❌ ChromeDriver installation failed"
        return 1
    fi
    
    # Test Selenium (if Python is available)
    if command -v python3 > /dev/null 2>&1; then
        if python3 -c "import selenium; print('Selenium version:', selenium.__version__)" > /dev/null 2>&1; then
            print_status "✅ Selenium installation successful"
        else
            print_warning "⚠️  Selenium installation may have failed"
        fi
    fi
}

# Main installation process
main() {
    print_status "Starting Chrome installation for Linux Selenium automation..."
    
    # Run installation steps
    install_system_dependencies
    install_chrome
    install_chromedriver
    install_python_dependencies
    create_symlinks
    setup_virtual_display
    
    # Test installation
    if test_installation; then
        print_status "🎉 Installation completed successfully!"
        echo ""
        echo "Next steps:"
        echo "1. Restart your terminal or run: source ~/.bashrc"
        echo "2. Run your Selenium tests with: python3 your_test.py"
        echo "3. For headless mode, ensure your test uses: --headless=new"
    else
        print_error "Installation completed with errors. Please check the output above."
        exit 1
    fi
}

# Run main function
main "$@"