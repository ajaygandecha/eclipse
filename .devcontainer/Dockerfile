FROM klee/klee:3.0

ENV TZ=America/New_York
ENV DEBIAN_FRONTEND=noninteractive

# The KLEE image defaults to the non-root `klee` user; switch to root for setup.
USER root

# Create workspace directory that will be mounted from the host
RUN mkdir -p /workspace
WORKDIR /workspace

# Install useful system utilities and Python tooling on top of the KLEE image.
# The upstream image can include Kitware apt entries without imported keys.
RUN rm -f /etc/apt/sources.list.d/kitware*.list /etc/apt/sources.list.d/archive_uri-https_apt_kitware_com_ubuntu-* \
    && for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do \
        if [ -f "$f" ]; then \
          sed -i '/apt\.kitware\.com/d' "$f"; \
        fi; \
      done \
    && apt-get update \
    && apt-get install --yes \
        apt-transport-https \
        build-essential \
        ca-certificates \
        curl \
        debian-keyring \
        debian-archive-keyring \
        git \
        gnupg \
        locales \
        python3 \
        python3-venv \
        python3-pip \
        software-properties-common \
        sudo \
        tzdata \
        wget \
        zsh \
    && rm -rf /var/lib/apt/lists/*

# Configure git for VS Code usage inside the container
RUN git config --system core.editor "code --wait" \
    && git config --system safe.directory '/workspace'

# Configure zsh and niceties for the default KLEE user
USER klee
ENV HOME=/home/klee

RUN curl https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh | bash - \
    && sed -i 's/robbyrussell/kennethreitz/g' ~/.zshrc \
    && echo 'export PATH=$PATH:$HOME/.local/bin' >> ~/.zshrc

# Set Locale for functional autocompletion in zsh
USER root
RUN locale-gen en_US.UTF-8

# Default back to the non-root KLEE user for development
USER klee
WORKDIR /workspace
