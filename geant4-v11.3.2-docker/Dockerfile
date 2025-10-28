FROM debian:13

LABEL maintainer="Yanzhen Guo<yzhguo@mail.ustc.edu.cn>" \
      version="1.0" \
      description="This is a docker image for Geant4 development environment (with Qt5 and VTK support)." \
      project="Geant"

ENV DEBIAN_FRONTEND=noninteractive \
    GEANT4_INSTALL_DIR=/work/geant4-install \
    SSH_PASSWORD=geant4

RUN rm -rf /etc/apt/sources.list.d || true
COPY sources.list /etc/apt/sources.list

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y \
    sudo \
    build-essential \
    net-tools \
    git \
    cmake \
    wget \
    curl \
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
    libvtk9-qt-dev

RUN rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/run/sshd && \
    echo "root:$SSH_PASSWORD" | chpasswd && \
    echo PermitRootLogin yes >> /etc/ssh/sshd_config.d/login.conf && \
    echo PasswordAuthentication yes >> /etc/ssh/sshd_config.d/login.conf

COPY ./ssh_banner.txt /etc/ssh/ssh_banner.txt
RUN echo "Banner /etc/ssh/ssh_banner.txt" >> /etc/ssh/sshd_config

EXPOSE 22

RUN cat /etc/ssh/sshd_config

WORKDIR /tmp
RUN wget https://coder.com/install.sh
RUN bash ./install.sh

EXPOSE 8080

RUN mkdir -p /work
WORKDIR /work

RUN wget https://gitlab.cern.ch/geant4/geant4/-/archive/v11.3.2/geant4-v11.3.2.tar.gz && \
    tar -xzf geant4-v11.3.2.tar.gz && \
    mkdir -p geant4-build geant4-install && \
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
    # 配置 C/C++ 插件识别：设置 CPATH（头文件路径）和 LIBRARY_PATH（库路径）
    echo "export CPATH=\$CPATH:$GEANT4_INSTALL_DIR/include" >> /root/.bashrc && \
    echo "export LIBRARY_PATH=\$LIBRARY_PATH:$GEANT4_INSTALL_DIR/lib" >> /root/.bashrc

RUN echo "#!/bin/bash" > /start.sh && \
    echo "service ssh start" >> /start.sh && \
    # code-server 允许所有地址访问（--bind-addr 0.0.0.0:8080），禁用密码（--auth none，简化测试）
    echo "code-server --bind-addr 0.0.0.0:8080 --auth none /work" >> /start.sh && \
    chmod +x /start.sh

CMD ["/start.sh"]
