#!/bin/bash

# System Dependencies Installation Script for Selenium Automation
# This script installs all required system dependencies for running Selenium automation on Linux servers

set -e  # Exit on any error

echo "🔧 Installing system dependencies for Selenium automation on Linux..."

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo $ID
    elif [ -f /etc/redhat-release ]; then
        if grep -q "CentOS" /etc/redhat-release; then
            echo "centos"
        elif grep -q "Red Hat" /etc/redhat-release; then
            echo "rhel"
        elif grep -q "Fedora" /etc/redhat-release; then
            echo "fedora"
        else
            echo "rhel"
        fi
    else
        echo "unknown"
    fi
}

# Update package manager
update_package_manager() {
    local distro=$(detect_distro)
    print_step "Updating package manager..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get update
            ;;
        centos|rhel|fedora)
            sudo yum update -y || sudo dnf update -y
            ;;
        *)
            print_warning "Unknown distribution. Skipping package manager update."
            ;;
    esac
}

# Install essential system packages
install_essential_packages() {
    local distro=$(detect_distro)
    print_step "Installing essential system packages..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
                curl \
                wget \
                gnupg \
                ca-certificates \
                software-properties-common \
                apt-transport-https \
                lsb-release \
                gnupg-agent \
                software-properties-common \
                apt-transport-https \
                lsb-release \
                gnupg-agent
            ;;
        centos|rhel|fedora)
            sudo yum install -y \
                curl \
                wget \
                gnupg2 \
                ca-certificates \
                yum-utils || \
                sudo dnf install -y \
                curl \
                wget \
                gnupg2 \
                ca-certificates \
                dnf-plugins-core
            ;;
        *)
            print_warning "Unknown distribution. Installing basic packages..."
            sudo yum install -y curl wget gnupg2 ca-certificates || \
            sudo apt-get install -y curl wget gnupg2 ca-certificates
            ;;
    esac
}

# Install desktop environment packages for GUI mode
install_desktop_packages() {
    local distro=$(detect_distro)
    print_step "Installing desktop environment packages..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
                xvfb \
                x11vnc \
                x11-xkb-utils \
                xfonts-100dpi \
                xfonts-75dpi \
                xfonts-scalable \
                xserver-xorg-core \
                xserver-xorg-video-dummy \
                libx11-dev \
                libxext-dev \
                libxrandr-dev \
                libxrender-dev \
                libxi-dev \
                libxss-dev \
                libgconf-2-4 \
                libnss3-dev
            ;;
        centos|rhel|fedora)
            sudo yum install -y \
                xorg-x11-server-Xvfb \
                xorg-x11-server-Xorg \
                xorg-x11-xauth \
                xorg-x11-fonts-Type1 \
                xorg-x11-fonts-misc \
                libX11 \
                libXext \
                libXrandr \
                libXrender \
                libXi \
                libXScrnSaver \
                libXScrnSaver-devel \
                libXcursor \
                libXcursor-devel || \
                sudo dnf install -y \
                xorg-x11-server-Xvfb \
                xorg-x11-server-Xorg \
                xorg-x11-xauth \
                xorg-x11-fonts-Type1 \
                xorg-x11-fonts-misc \
                libX11 \
                libXext \
                libXrandr \
                libXrender \
                libXi \
                libXScrnSaver \
                libXScrnSaver-devel \
                libXcursor \
                libXcursor-devel
            ;;
        *)
            print_warning "Unknown distribution. Skipping desktop packages."
            ;;
    esac
}

# Install Chrome dependencies
install_chrome_dependencies() {
    local distro=$(detect_distro)
    print_step "Installing Chrome-specific dependencies..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
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
                libappindicator1 \
                libsecret-1-0 \
                libnotify4 \
                libgconf-2-4
            ;;
        centos|rhel|fedora)
            sudo yum install -y \
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
                vulkan \
                libappindicator \
                libnotify \
                libsecret \
                pango || \
                sudo dnf install -y \
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
                vulkan \
                libappindicator \
                libnotify \
                libsecret \
                pango
            ;;
        *)
            print_warning "Unknown distribution. Skipping Chrome dependencies."
            ;;
    esac
}

# Install network and security packages
install_network_security_packages() {
    local distro=$(detect_distro)
    print_step "Installing network and security packages..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
                openssl \
                stunnel4 \
                net-tools \
                netcat-openbsd \
                telnet \
                tcpdump \
                nmap \
                iptables-persistent
            ;;
        centos|rhel|fedora)
            sudo yum install -y \
                openssl \
                stunnel \
                net-tools \
                nmap-ncat \
                telnet \
                tcpdump \
                nmap \
                iptables-services || \
                sudo dnf install -y \
                openssl \
                stunnel \
                net-tools \
                nmap-ncat \
                telnet \
                tcpdump \
                nmap \
                iptables
            ;;
        *)
            print_warning "Unknown distribution. Skipping network packages."
            ;;
    esac
}

# Install development tools
install_dev_tools() {
    local distro=$(detect_distro)
    print_step "Installing development tools..."
    
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
                build-essential \
                gcc \
                g++ \
                make \
                cmake \
                git \
                vim \
                tree \
                htop \
                unzip \
                zip \
                tar \
                gzip \
                bzip2 \
                p7zip \
                sqlite3 \
                postgresql-client \
                mysql-client \
                chromium-chromedriver
            ;;
        centos|rhel|fedora)
            sudo yum groupinstall -y "Development Tools" || \
            sudo dnf groupinstall -y "Development Tools"
            sudo yum install -y \
                gcc \
                gcc-c++ \
                make \
                cmake \
                git \
                vim \
                tree \
                htop \
                unzip \
                zip \
                tar \
                gzip \
                bzip2 \
                p7zip \
                sqlite \
                postgresql \
                mysql \
                chromedriver || \
            sudo dnf install -y \
                gcc \
                gcc-c++ \
                make \
                cmake \
                git \
                vim \
                tree \
                htop \
                unzip \
                zip \
                tar \
                gzip \
                bzip2 \
                p7zip \
                sqlite \
                postgresql \
                mysql \
                chromedriver
            ;;
        *)
            print_warning "Unknown distribution. Skipping development tools."
            ;;
    esac
}

# Install Python environment
install_python_env() {
    print_step "Setting up Python environment..."
    
    # Install Python 3 and pip
    local distro=$(detect_distro)
    case $distro in
        ubuntu|debian)
            sudo apt-get install -y \
                python3 \
                python3-pip \
                python3-dev \
                python3-venv \
                python3-wheel
            ;;
        centos|rhel|fedora)
            sudo yum install -y \
                python3 \
                python3-pip \
                python3-devel \
                python3-virtualenv || \
            sudo dnf install -y \
                python3 \
                python3-pip \
                python3-devel \
                python3-virtualenv
            ;;
        *)
            # Try generic installation
            sudo yum install -y python3 python3-pip || \
            sudo apt-get install -y python3 python3-pip
            ;;
    esac
    
    # Create symlinks for python
    sudo ln -sf /usr/bin/python3 /usr/bin/python
    
    print_status "Python version:"
    python --version
    pip --version
}

# Install Python dependencies for Selenium
install_selenium_dependencies() {
    print_step "Installing Python dependencies for Selenium..."
    
    # Upgrade pip first
    pip3 install --user --upgrade pip
    
    # Install Selenium and related packages
    pip3 install --user --upgrade \
        selenium \
        webdriver-manager \
        beautifulsoup4 \
        requests \
        lxml \
        openpyxl \
        pandas \
        psutil \
        pyautogui \
        pillow \
        numpy \
        scipy \
        matplotlib \
        plotly \
        flask \
        flask-socketio \
        eventlet \
        gevent
    
    # Install additional useful packages
    pip3 install --user --upgrade \
        jupyter \
        ipython \
        pytest \
        pytest-html \
        pytest-selenium \
        pytest-allure-adaptor \
        allure-pytest
    
    print_status "Selenium dependencies installed successfully"
}

# Setup virtual display (Xvfb)
setup_virtual_display() {
    print_step "Setting up virtual display (Xvfb)..."
    
    # Check if Xvfb is installed
    if ! command -v Xvfb > /dev/null 2>&1; then
        print_warning "Xvfb not found. Please install desktop packages first."
        return 1
    fi
    
    # Check if Xvfb is already running
    if pgrep -f "Xvfb" > /dev/null; then
        print_status "Xvfb is already running"
        return 0
    fi
    
    # Start Xvfb on display :99 (standard for headless operations)
    print_status "Starting Xvfb on display :99..."
    Xvfb :99 -screen 0 1920x1080x24 > /dev/null 2>&1 &
    
    # Wait a moment for Xvfb to start
    sleep 2
    
    # Verify Xvfb is running
    if pgrep -f "Xvfb" > /dev/null; then
        print_status "Xvfb started successfully"
        
        # Set DISPLAY environment variable
        export DISPLAY=:99
        echo "export DISPLAY=:99" >> ~/.bashrc
        print_status "DISPLAY environment variable set to :99"
    else
        print_error "Failed to start Xvfb"
        return 1
    fi
}

# Setup firewall rules (basic)
setup_firewall() {
    print_step "Setting up basic firewall rules..."
    
    local distro=$(detect_distro)
    
    case $distro in
        ubuntu|debian)
            # Ubuntu uses ufw
            if command -v ufw > /dev/null 2>&1; then
                sudo ufw --force enable
                sudo ufw allow ssh
                sudo ufw allow 80/tcp
                sudo ufw allow 443/tcp
                print_status "UFW firewall configured"
            fi
            ;;
        centos|rhel|fedora)
            # RHEL/CentOS/Fedora use firewalld or iptables
            if command -v firewall-cmd > /dev/null 2>&1; then
                sudo systemctl start firewalld
                sudo systemctl enable firewalld
                sudo firewall-cmd --permanent --add-service=ssh
                sudo firewall-cmd --permanent --add-service=http
                sudo firewall-cmd --permanent --add-service=https
                sudo firewall-cmd --reload
                print_status "Firewalld configured"
            fi
            ;;
        *)
            print_warning "Unknown distribution. Skipping firewall setup."
            ;;
    esac
}

# Create necessary directories
create_directories() {
    print_step "Creating necessary directories..."
    
    # Create directories for automation
    mkdir -p ~/selenium_tests
    mkdir -p ~/chrome_downloads
    mkdir -p ~/automation_logs
    mkdir -p ~/.local/bin
    
    print_status "Directories created successfully"
}

# Configure system limits
configure_system_limits() {
    print_step "Configuring system limits for automation..."
    
    # Increase file descriptor limits
    sudo bash -c 'cat >> /etc/security/limits.conf << EOF
# Selenium Automation Limits
* soft nofile 65536
* hard nofile 65536
* soft nproc 32768
* hard nproc 32768
root soft nofile 65536
root hard nofile 65536
root soft nproc 32768
root hard nproc 32768
EOF'
    
    # Update sysctl for better network performance
    sudo bash -c 'cat >> /etc/sysctl.conf << EOF
# Selenium Automation Network Settings
net.core.somaxconn = 65536
net.ipv4.tcp_max_syn_backlog = 65536
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_probes = 10
net.ipv4.tcp_keepalive_intvl = 30
EOF'
    
    # Apply sysctl settings
    sudo sysctl -p
    
    print_status "System limits configured"
}

# Test system setup
test_system_setup() {
    print_step "Testing system setup..."
    
    # Test Xvfb
    if command -v Xvfb > /dev/null 2>&1; then
        if pgrep -f "Xvfb" > /dev/null; then
            print_status "✅ Xvfb is running"
        else
            print_warning "⚠️  Xvfb is installed but not running"
        fi
    else
        print_warning "⚠️  Xvfb is not installed"
    fi
    
    # Test Python
    if command -v python3 > /dev/null 2>&1; then
        python_version=$(python3 --version)
        print_status "✅ Python3 installed: $python_version"
    else
        print_error "❌ Python3 not found"
    fi
    
    # Test pip
    if command -v pip3 > /dev/null 2>&1; then
        print_status "✅ pip3 installed"
    else
        print_error "❌ pip3 not found"
    fi
    
    # Test selenium installation
    if python3 -c "import selenium; print('Selenium version:', selenium.__version__)" > /dev/null 2>&1; then
        selenium_version=$(python3 -c "import selenium; print(selenium.__version__)")
        print_status "✅ Selenium installed: $selenium_version"
    else
        print_warning "⚠️  Selenium not installed or not working"
    fi
    
    # Test Chrome installation
    if command -v google-chrome > /dev/null 2>&1; then
        chrome_version=$(google-chrome --version 2>/dev/null || echo "version unknown")
        print_status "✅ Chrome installed: $chrome_version"
    else
        print_warning "⚠️  Chrome not installed"
    fi
    
    # Test ChromeDriver installation
    if command -v chromedriver > /dev/null 2>&1; then
        driver_version=$(chromedriver --version 2>/dev/null || echo "version unknown")
        print_status "✅ ChromeDriver installed: $driver_version"
    else
        print_warning "⚠️  ChromeDriver not installed"
    fi
    
    # Test DISPLAY variable
    if [ -n "$DISPLAY" ]; then
        print_status "✅ DISPLAY variable set: $DISPLAY"
    else
        print_warning "⚠️  DISPLAY variable not set"
    fi
}

# Main installation function
main() {
    echo ""
    echo "================================================"
    echo "🔧 LINUX SELENIUM AUTOMATION DEPENDENCIES INSTALLER"
    echo "================================================"
    echo ""
    
    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_warning "Running as root. This is not recommended for development environments."
    fi
    
    # Detect distribution
    local distro=$(detect_distro)
    print_status "Detected Linux distribution: $distro"
    echo ""
    
    # Run installation steps
    update_package_manager
    install_essential_packages
    install_desktop_packages
    install_chrome_dependencies
    install_network_security_packages
    install_dev_tools
    install_python_env
    install_selenium_dependencies
    setup_virtual_display
    setup_firewall
    create_directories
    configure_system_limits
    
    echo ""
    echo "================================================"
    print_step "TESTING SYSTEM SETUP"
    echo "================================================"
    test_system_setup
    
    echo ""
    echo "================================================"
    print_status "🎉 INSTALLATION COMPLETED!"
    echo "================================================"
    echo ""
    echo "Next steps:"
    echo "1. Restart your terminal: exec bash"
    echo "2. Run Chrome installation: ./install_chrome_linux.sh"
    echo "3. Test Selenium: python3 -c 'from selenium import webdriver; print(\"Selenium ready!\")'"
    echo "4. Run your automation tests!"
    echo ""
    echo "Environment variables to check:"
    echo "- DISPLAY: $DISPLAY"
    echo "- Python: $(python3 --version 2>/dev/null || echo 'not installed')"
    echo ""
}

# Run main function
main "$@"