# Base stage with common dependencies
FROM python:3.11-slim AS base
SHELL ["/bin/bash", "-c"]

# Set environment variables to make Python print directly to the terminal and avoid .pyc files.
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies required for package manager and build tools.
# sudo, wget, zip needed for some assistants, like junie
# libgmp-dev, libtinfo-dev, libncurses-dev needed for Haskell (GHC/HLS)
# binutils, libcurl4-openssl-dev, libedit2, libsqlite3-0, libxml2-dev,
#   libz3-dev, pkg-config, zlib1g-dev needed for Swift runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    ssh \
    sudo \
    wget \
    zip \
    unzip \
    sed \
    # Haskell (GHC/HLS) dependencies \
    libgmp-dev \
    libtinfo-dev \
    libncurses-dev \
    # Swift runtime dependencies \
    binutils \
    libc6-dev \
    libcurl4-openssl-dev \
    libedit2 \
    libgcc-s1 \
    libpython3-dev \
    libsqlite3-0 \
    libstdc++-12-dev \
    libxml2-dev \
    libz3-dev \
    pkg-config \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pipx.
RUN python3 -m pip install --no-cache-dir pipx \
    && pipx ensurepath

# Install nodejs
ENV NVM_VERSION=0.40.3
ENV NODE_VERSION=22.18.0
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh | bash
# standard location
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/:${PATH}"

# Add local bin to the path
ENV PATH="${PATH}:/root/.local/bin"

# Install the latest version of uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# =============================================================================
# Language Server Protocol (LSP) Installations
# Serena uses these for polyglot code analysis
# =============================================================================

# --- RUST: rust-analyzer (via rustup) ---
# Serena looks for: rustup which rust-analyzer -> ~/.cargo/bin/rust-analyzer
ENV RUSTUP_HOME=/usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo
ENV PATH="${CARGO_HOME}/bin:${PATH}"
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    --default-toolchain stable \
    --profile minimal \
    && rustup component add rust-analyzer

# --- HASKELL: haskell-language-server-wrapper (via GHCup) ---
# Serena looks for: ~/.ghcup/bin/haskell-language-server-wrapper
# Project uses GHC 9.8.4 (lts-23.0)
ENV GHCUP_INSTALL_BASE_PREFIX=/root
RUN curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | \
    BOOTSTRAP_HASKELL_NONINTERACTIVE=1 \
    BOOTSTRAP_HASKELL_GHC_VERSION=9.8.4 \
    BOOTSTRAP_HASKELL_INSTALL_HLS=1 \
    BOOTSTRAP_HASKELL_INSTALL_STACK=0 \
    BOOTSTRAP_HASKELL_ADJUST_BASHRC=0 \
    sh
ENV PATH="/root/.ghcup/bin:${PATH}"

# --- SWIFT: sourcekit-lsp (via Swift toolchain tarball) ---
# Serena looks for: sourcekit-lsp in PATH
# Using Ubuntu 22.04 tarball (compatible with Debian bookworm, same glibc generation)
ENV SWIFT_VERSION=6.2.3
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
      SWIFT_PLATFORM="ubuntu2204-aarch64"; \
      SWIFT_SUFFIX="-aarch64"; \
    else \
      SWIFT_PLATFORM="ubuntu2204"; \
      SWIFT_SUFFIX=""; \
    fi && \
    SWIFT_URL="https://download.swift.org/swift-${SWIFT_VERSION}-release/${SWIFT_PLATFORM}/swift-${SWIFT_VERSION}-RELEASE/swift-${SWIFT_VERSION}-RELEASE-ubuntu22.04${SWIFT_SUFFIX}.tar.gz" && \
    echo "Downloading Swift from: $SWIFT_URL" && \
    curl -sL "$SWIFT_URL" -o swift.tar.gz && \
    mkdir -p /opt/swift && \
    tar xzf swift.tar.gz --strip-components=1 -C /opt/swift && \
    rm swift.tar.gz
ENV PATH="/opt/swift/usr/bin:${PATH}"

# --- TYPESCRIPT: typescript-language-server (auto-installed by Serena via npm) ---
# --- BASH: bash-language-server (auto-installed by Serena via npm) ---
# Both auto-installed by Serena at runtime using Node.js/npm (already available above)

# Set the working directory
WORKDIR /workspaces/serena

# Copy all files for development
COPY . /workspaces/serena/

# Create Serena configuration
ENV SERENA_HOME=/workspaces/serena/config
RUN mkdir -p $SERENA_HOME
RUN cp src/serena/resources/serena_config.template.yml $SERENA_HOME/serena_config.yml
RUN sed -i 's/^gui_log_window: .*/gui_log_window: False/' $SERENA_HOME/serena_config.yml
RUN sed -i 's/^web_dashboard_listen_address: .*/web_dashboard_listen_address: 0.0.0.0/' $SERENA_HOME/serena_config.yml
RUN sed -i 's/^web_dashboard_open_on_launch: .*/web_dashboard_open_on_launch: False/' $SERENA_HOME/serena_config.yml

# Create virtual environment and install dependencies
RUN uv venv
RUN . .venv/bin/activate
RUN uv pip install -r pyproject.toml -e .

# --- PYTHON: pyright (Python LSP module) ---
# Serena runs: python -m pyright.langserver --stdio
RUN uv pip install pyright

ENV PATH="/workspaces/serena/.venv/bin:${PATH}"
# Ensure contracts/ package (at project root) is importable
ENV PYTHONPATH="/workspaces/serena:${PYTHONPATH}"

# Entrypoint to ensure environment is activated
ENTRYPOINT ["/bin/bash", "-c", "source .venv/bin/activate && $0 $@"]
