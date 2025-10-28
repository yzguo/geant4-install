#!/bin/bash
set -e

sudo apt update && sudo apt upgrade -y

# Basic
sudo apt install -y build-essential cmake wget git curl axel make gdb libexpat1-dev qtbase5-dev libvtk9-dev libvtk9-qt-dev

mkdir -p $HOME/geant4
cd $HOME/geant4/

axel -n 32 https://gitlab.cern.ch/geant4/geant4/-/archive/v11.3.2/geant4-v11.3.2.tar.gz
tar -xzf geant4-v11.3.2.tar.gz
mkdir -p geant4-build geant4-install
cd geant4-build/

cmake -DCMAKE_INSTALL_PREFIX=$HOME/geant4/geant4-install \
      -DGEANT4_INSTALL_DATA=ON \
      -DGEANT4_USE_QT=ON \
      -DGEANT4_USE_VTK=ON \
      $HOME/geant4/geant4-v11.3.2

make -j$(nproc)
make install

source $HOME/geant4/geant4-install/bin/geant4.sh
echo "source $HOME/geant4/geant4-install/bin/geant4.sh" >> $HOME/.bashrc

echo "Geant4 安装完成!请重启终端或执行 source $HOME/.bashrc 生效!"

rm -rf $HOME/geant4/geant4-v11.3.2.tar.gz
rm -rf $HOME/geant4/geant4-build
