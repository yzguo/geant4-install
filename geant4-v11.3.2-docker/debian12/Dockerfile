FROM debian:12

LABEL maintainer="Yanzhen Guo<yzhguo@mail.ustc.edu.cn>" \
      version="1.0" \
      description="This is a docker image for Geant4 development environment (with Qt5 and VTK support)." \
      project="Geant4"

ENV DEBIAN_FRONTEND=noninteractive \
    GEANT4_INSTALL_DIR=/work/geant4 \
    SSH_PASSWORD=geant4

RUN rm -rf /etc/apt/sources.list.d || true
COPY sources.list /etc/apt/sources.list

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y \
    sudo \
    build-essential \
    net-tools \
    ca-certificates \
    locales \
    git \
    cmake \
    wget \
    curl \
    axel \
    bash \
    make \
    vim \
    nano \
    gdb \
    ncdu \
    openssh-server \
    openssh-client \
    libexpat1-dev \
    qtbase5-dev \
    libvtk9-dev \
    libvtk9-qt-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    freeglut3-dev \
    mesa-utils \
    mesa-common-dev \
    libglew-dev \
    libglfw3-dev

RUN rm -rf /var/lib/apt/lists/* && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen en_US.UTF-8

RUN mkdir -p /var/run/sshd && \
    echo "root:$SSH_PASSWORD" | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

COPY ./ssh_banner.txt /etc/ssh/ssh_banner.txt
RUN echo "Banner /etc/ssh/ssh_banner.txt" >> /etc/ssh/sshd_config

EXPOSE 22

RUN mkdir -p /work
WORKDIR /work

RUN axel -n 256 -o geant4-v11.3.2.tar.gz https://gitlab.cern.ch/geant4/geant4/-/archive/v11.3.2/geant4-v11.3.2.tar.gz

RUN tar -xzf geant4-v11.3.2.tar.gz && \
    mkdir -p geant4 geant4-build && \
    cd geant4-build && \
    cmake -DCMAKE_INSTALL_PREFIX=$GEANT4_INSTALL_DIR \
          -DGEANT4_INSTALL_DATA=ON \
          -DGEANT4_USE_QT=ON \
          -DGEANT4_USE_VTK=ON \
          /work/geant4-v11.3.2 && \
    make -j$(nproc) && \
    make install && \
    cd /work && rm -rf geant4-v11.3.2.tar.gz geant4-build

RUN echo "export GEANT4_INSTALL_DIR=$GEANT4_INSTALL_DIR" >> /root/.bashrc && \
    echo "source $GEANT4_INSTALL_DIR/bin/geant4.sh" >> /root/.bashrc && \
    echo "export CPATH=\$CPATH:$GEANT4_INSTALL_DIR/include" >> /root/.bashrc && \
    echo "export LIBRARY_PATH=\$LIBRARY_PATH:$GEANT4_INSTALL_DIR/lib" >> /root/.bashrc && \
    echo "export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:$GEANT4_INSTALL_DIR/lib" >> /root/.bashrc

CMD ["/usr/sbin/sshd", "-D"]
